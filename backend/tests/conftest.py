"""Shared test fixtures.

Every test here runs offline: the LLM provider is replaced with a scripted
fake, so the suite never needs an API key and never spends credit.
"""
import os
import pathlib
import sys

import pytest

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Point the app at a throwaway database before anything imports the engine.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class FakeProvider:
    """Replays a scripted list of responses instead of calling an API.

    Each scripted entry is either a dict of overrides or a callable taking
    (messages, tools). Calls are recorded so tests can assert on what the agent
    actually sent - notably whether tool schemas were included.
    """

    def __init__(self, responses=None, model="fake-model"):
        self.responses = list(responses or [])
        self.model = model
        self.calls = []

    def _default(self):
        return {
            "content": "ok",
            "tool_calls": [],
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "duration_ms": 1.0,
            "model": self.model,
            "cost": 0.0,
            "cost_known": True,
            "error": None,
        }

    def generate(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})

        if not self.responses:
            return self._default()

        scripted = self.responses.pop(0)
        if callable(scripted):
            scripted = scripted(messages, tools)

        result = self._default()
        result.update(scripted)
        return result


def tool_call(call_id, name, arguments):
    """Build a tool call in the shape a provider returns."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


@pytest.fixture
def fake_provider(monkeypatch):
    """Install a FakeProvider everywhere get_provider() is used."""

    def _install(responses=None, model="fake-model"):
        provider = FakeProvider(responses, model=model)
        monkeypatch.setattr("app.agent.agent.get_provider", lambda *a, **k: provider)
        monkeypatch.setattr("app.agent.context_manager.get_provider", lambda *a, **k: provider)
        return provider

    return _install


@pytest.fixture
def db_session():
    """A fresh in-memory database per test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database.database import Base
    from app.models import models  # noqa: F401 - registers the tables

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def tracer(db_session):
    from app.tracing.collector import TraceCollector

    collector = TraceCollector(session=db_session)
    collector.start_run("test_conversation")
    return collector
