# GlassBox AI
"See exactly what your AI did."

## Overview
GlassBox AI is an observable AI agent platform built to solve the "Glass Box Problem."
It ensures that the complete execution of an AI agent can be inspected, explained, measured and debugged.

Unlike generic chatbot wrappers, GlassBox AI exposes its entire internal pipeline through a custom real-time telemetry frontend. It features a strict "aircraft black-box" aesthetic that presents highly dense data—showing you precisely what context was injected, what tools were called, and how much each step cost.

## Core Features
- **Bounded Context Management:** Enforces a configurable token budget (default 8,000), counting tokens locally with `tiktoken` before the request goes out, summarising whatever it has to drop, and reporting the measured reduction.
- **Native Tool Calling:** Tool schemas are sent to the model, and every call is validated against its schema before execution. Invalid calls are returned to the model as errors so it can replan.
- **Inline RAG Pipeline:** Intercepts each query, chunks the internal knowledge base (`docs/`), scores passages by term frequency, and injects the best matches into the system prompt.
- **Trace Execution Engine:** Every step of the agent loop is written to SQLite via SQLAlchemy, capturing execution times, token counts, costs, error states and tool arguments.
- **Honest Cost Accounting:** Prices come from `backend/pricing.json`. A model with no known price is reported as *unknown*, never as $0.00.
- **Trace Export:** Any run downloads as a single `glassbox.trace.v1` JSON document.
- **Session Continuation:** Reconstructs past chat histories from backend traces, so old conversations can be revisited and continued from the "Sessions" sidebar.
- **Flight Recorder UI:** A dense, 1px-hairline React frontend designed for utility and observability rather than SaaS aesthetics.

## Tech Stack
- **Backend:** Python, FastAPI, SQLAlchemy, SQLite
- **Frontend:** React, TypeScript, Tailwind CSS, Vite
- **Model:** Any OpenAI-compatible endpoint. Configured by default for Gemini through its OpenAI-compatible API, which gives native tool calling.

## Getting Started

### 1. Backend Setup

```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

**Environment Variables:**
Copy `backend/.env.example` to `backend/.env` and add your key. The example file documents every setting; the minimum is:

```env
LLM_PROVIDER=openai
LLM_API_KEY=your_gemini_api_key_here
LLM_MODEL=gemini-2.5-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
DATABASE_URL=sqlite:///./glassbox.db
```

If your model is not listed in `backend/pricing.json`, either add it there or set `LLM_PRICE_INPUT` / `LLM_PRICE_OUTPUT` (USD per 1M tokens). Otherwise cost is reported as unknown rather than as zero.

Start the backend:
```bash
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Navigate to `http://localhost:5173`. To point the UI at a different backend, set `VITE_API_BASE_URL` (see `frontend/.env.example`).

## Tests

The backend suite runs entirely offline — the LLM provider is replaced with a scripted fake, so no API key is needed and no credit is spent.

```bash
cd backend
python -m pytest
```

For a live end-to-end check against the real API (this does spend credit):

```bash
python scripts/smoke_check.py "What is 25 * 4?"
```

Frontend checks:

```bash
cd frontend
npx tsc -b && npx oxlint && npm run build
```

## Configuration Reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `openai` | `openai` (incl. OpenAI-compatible endpoints) or `gemini` |
| `LLM_MODEL` | `gpt-4o-mini` | Model id |
| `LLM_BASE_URL` | OpenAI | API base URL |
| `LLM_PRICE_INPUT` / `LLM_PRICE_OUTPUT` | unset | Price override, USD per 1M tokens |
| `CONTEXT_MAX_TOKENS` | `8000` | Per-request token budget |
| `AGENT_MAX_RETRIES` | `3` | Replans allowed after a failure |
| `AGENT_MAX_STEPS` | `8` | Total LLM calls per request |
| `DATABASE_URL` | local SQLite | Trace database |
| `CORS_ORIGINS` | localhost:5173 | Allowed frontend origins |
| `ENABLE_TEST_ENDPOINTS` | `true` | Enables `/api/tests/*`, which spend real credit |

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Status plus the active model and budget |
| `POST /api/chat` | Run an agent turn |
| `GET /api/runs` | List runs (paginated) |
| `GET /api/runs/{id}` | One run |
| `GET /api/runs/{id}/traces` | Ordered trace steps |
| `GET /api/runs/{id}/export` | Full trace as a downloadable JSON document |
| `DELETE /api/runs/{id}` | Delete a run and its steps |
| `GET /api/stats/models` | Per-model token and cost totals |
| `GET /api/conversations` | Chat sessions |
| `GET /api/conversations/{id}/history` | Reconstructed history |
| `POST /api/tests/failure-wrong-tool` | Validator recovery drill |
| `POST /api/tests/stress-test` | Context compaction drill |

## Documentation
See the `docs/` folder:
- **ARCHITECTURE.md**: Components and the request lifecycle.
- **OBSERVABILITY.md**: Step types, run counters and cost accounting.
- **CONTEXT_ENGINEERING.md**: The token budget and the context lifecycle.
- **FAILURES.md**: Validation, the replan loop and its bounds.
- **REPLAY.md**: Trace export, and the replay engine as an open item.
- **DEMO.md**: A walkthrough of the features.

## Collaborators

- [Garvit Dalakoti](https://github.com/skysoart)
- [Dhruv Tilara](https://github.com/Dhruvtilara)
- [Khushal Jangid](https://github.com/khushal123supreme)
