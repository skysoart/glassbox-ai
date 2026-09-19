"""Central configuration.

This module MUST be imported before any module that reads environment
variables at import time (notably ``app.database.database``), because it is
what loads the ``.env`` file. Importing it has the side effect of populating
``os.environ``; that is deliberate and is why it is imported first everywhere.
"""
import os
import pathlib

from dotenv import load_dotenv

# backend/app/config.py -> backend/
BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Load backend/.env explicitly so the values are present no matter which
# directory the process was started from.
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float):
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# --- LLM -------------------------------------------------------------------
LLM_PROVIDER = _env("LLM_PROVIDER", "openai").lower()
LLM_API_KEY = _env("LLM_API_KEY", "")
LLM_MODEL = _env("LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = _env("LLM_BASE_URL", "https://api.openai.com/v1")

# Optional manual price override (USD per 1M tokens) for the configured model.
# Use these when running a model that is not in pricing.json.
LLM_PRICE_INPUT = _env_float("LLM_PRICE_INPUT", None)
LLM_PRICE_OUTPUT = _env_float("LLM_PRICE_OUTPUT", None)
PRICING_FILE = _env("LLM_PRICING_FILE", str(BACKEND_DIR / "pricing.json"))

# --- Agent -----------------------------------------------------------------
# Token budget the ContextManager is allowed to spend on a single request.
CONTEXT_MAX_TOKENS = _env_int("CONTEXT_MAX_TOKENS", 8000)
# How many times the agent may replan after a validation/tool failure.
AGENT_MAX_RETRIES = _env_int("AGENT_MAX_RETRIES", 3)
# Hard ceiling on LLM calls per request, so a model that keeps requesting
# tools cannot loop forever.
AGENT_MAX_STEPS = _env_int("AGENT_MAX_STEPS", 8)

# --- Storage ---------------------------------------------------------------
DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'glassbox.db'}")

# --- RAG -------------------------------------------------------------------
DOCS_DIR = _env("DOCS_DIR", str(PROJECT_ROOT / "docs"))

# --- API -------------------------------------------------------------------
# Comma-separated list of allowed origins. "*" is accepted for local dev.
CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
# The /api/tests/* endpoints spend real API credit; they are opt-in.
ENABLE_TEST_ENDPOINTS = _env("ENABLE_TEST_ENDPOINTS", "true").lower() in ("1", "true", "yes")
