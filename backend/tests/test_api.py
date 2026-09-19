import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """A TestClient whose database dependency points at a throwaway file."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.api.main as main
    from app.database.database import Base
    from app.models import models  # noqa: F401 - registers the tables

    url = "sqlite:///" + str(tmp_path / "test.db").replace("\\", "/")
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[main.get_db] = override_get_db
    try:
        with TestClient(main.app) as test_client:
            test_client.session_factory = TestingSession
            test_client.main = main
            yield test_client
    finally:
        main.app.dependency_overrides.clear()


def _seed_run(client, conversation_id="chat_ui_1"):
    from app.tracing.collector import TraceCollector

    session = client.session_factory()
    try:
        tracer = TraceCollector(session=session)
        run = tracer.start_run(conversation_id)
        tracer.add_step(step_type="USER_INPUT", input_data={"message": "hello"})
        tracer.add_step(
            step_type="LLM_CALL",
            output_data={"content": "hi", "tool_calls": []},
            token_usage={"prompt_tokens": 10, "completion_tokens": 3},
            cost=0.001,
            model="gemini-2.5-flash",
        )
        tracer.add_step(step_type="FINAL_RESPONSE", output_data={"content": "hi"})
        tracer.end_run("SUCCESS")
        return run.run_id
    finally:
        session.close()


def test_health_reports_configuration(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "model" in body and "context_budget_tokens" in body


def test_runs_list_and_detail(client):
    run_id = _seed_run(client)

    listed = client.get("/api/runs").json()
    assert any(r["run_id"] == run_id for r in listed)
    assert "cost_known" in listed[0]

    detail = client.get("/api/runs/" + run_id).json()
    assert detail["total_tokens"] == 13
    assert detail["llm_call_count"] == 1


def test_runs_list_is_paginated(client):
    for _ in range(5):
        _seed_run(client)

    page = client.get("/api/runs", params={"limit": 2}).json()
    assert len(page) == 2

    assert client.get("/api/runs", params={"limit": 0}).status_code == 422


def test_missing_run_returns_404(client):
    assert client.get("/api/runs/does-not-exist").status_code == 404
    assert client.get("/api/runs/does-not-exist/export").status_code == 404


def test_traces_are_ordered(client):
    run_id = _seed_run(client)
    steps = client.get("/api/runs/" + run_id + "/traces").json()
    assert [s["step_number"] for s in steps] == [1, 2, 3]
    assert steps[0]["step_type"] == "USER_INPUT"


def test_export_returns_a_downloadable_document(client):
    run_id = _seed_run(client)

    response = client.get("/api/runs/" + run_id + "/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    payload = json.loads(response.content)
    assert payload["format"] == "glassbox.trace.v1"
    assert payload["run"]["run_id"] == run_id
    assert len(payload["steps"]) == 3


def test_conversation_history_is_reconstructed(client):
    _seed_run(client, conversation_id="chat_ui_abc")

    conversations = client.get("/api/conversations").json()
    assert any(c["conversation_id"] == "chat_ui_abc" for c in conversations)

    history = client.get("/api/conversations/chat_ui_abc/history").json()
    roles = [m["role"] for m in history["history"]]
    assert roles == ["user", "assistant"]


def test_test_endpoints_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(client.main.config, "ENABLE_TEST_ENDPOINTS", False)
    response = client.post("/api/tests/stress-test")
    assert response.status_code == 403


def test_chat_marks_a_recovered_run(client, monkeypatch):
    """A run that hit a failure but still answered is RECOVERED, not SUCCESS."""
    from conftest import FakeProvider, tool_call

    provider = FakeProvider([
        {"content": None, "tool_calls": [tool_call("c1", "send_email", "{}")]},
        {"content": "I cannot send email, but here is the answer."},
    ])
    monkeypatch.setattr("app.agent.agent.get_provider", lambda *a, **k: provider)
    monkeypatch.setattr("app.agent.context_manager.get_provider", lambda *a, **k: provider)

    response = client.post("/api/chat", json={
        "conversation_id": "chat_ui_recover",
        "message": "email my results",
        "history": [],
    })

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert client.get("/api/runs/" + run_id).json()["status"] == "RECOVERED"


def test_chat_accepts_memories(client, monkeypatch):
    """Memories were accepted by the agent but never exposed on the endpoint."""
    from conftest import FakeProvider

    provider = FakeProvider([{"content": "OMEGA-99"}])
    monkeypatch.setattr("app.agent.agent.get_provider", lambda *a, **k: provider)
    monkeypatch.setattr("app.agent.context_manager.get_provider", lambda *a, **k: provider)

    response = client.post("/api/chat", json={
        "conversation_id": "chat_ui_mem",
        "message": "what is the code?",
        "history": [],
        "memories": ["The secret project code is OMEGA-99."],
    })

    assert response.status_code == 200
    system_messages = [m for m in provider.calls[0]["messages"] if m["role"] == "system"]
    assert any("OMEGA-99" in m["content"] for m in system_messages)


def test_delete_removes_the_run_and_its_steps(client):
    """The Delete button used to only drop the row from React state."""
    run_id = _seed_run(client)
    assert client.get("/api/runs/" + run_id).status_code == 200

    assert client.delete("/api/runs/" + run_id).status_code == 200

    assert client.get("/api/runs/" + run_id).status_code == 404
    assert client.get("/api/runs/" + run_id + "/traces").json() == []
    assert client.delete("/api/runs/" + run_id).status_code == 404


def test_model_breakdown_groups_by_actual_model(client):
    """The cost page used to show one hardcoded model name."""
    _seed_run(client)
    _seed_run(client)

    breakdown = client.get("/api/stats/models").json()

    assert len(breakdown) == 1
    row = breakdown[0]
    assert row["model"] == "gemini-2.5-flash"
    assert row["calls"] == 2
    assert row["input_tokens"] == 20
    assert row["output_tokens"] == 6
    assert row["cost"] == pytest.approx(0.002)
