# Architecture

## Components

1. **Config (`backend/app/config.py`)**: Loads `backend/.env` and exposes every
   setting as a typed value. It is imported before any module that reads
   environment variables at import time, so configuration is never silently
   ignored.
2. **FastAPI Backend (`backend/app/api/main.py`)**: Serves the trace, chat,
   statistics and diagnostic endpoints.
3. **Context Manager (`backend/app/agent/context_manager.py`)**: Fits the
   request into the token budget, summarising whatever it has to drop.
4. **LLM Provider (`backend/app/agent/llm_provider.py`)**: Normalises OpenAI
   and Gemini responses into one result shape, including token usage and cost.
5. **Validator (`backend/app/agent/validator.py`)**: Checks each tool call
   against the tool schema before it is executed.
6. **TraceCollector (`backend/app/tracing/collector.py`)**: Writes every step to
   SQLite through SQLAlchemy and maintains the per-run counters.
7. **React Frontend (`frontend/src`)**: Reads the HTTP API (not the database
   directly) and renders the trace, cost and incident views.

## Request Lifecycle

1. User submits a request; `USER_INPUT` is recorded.
2. The inline RAG pass searches `docs/` and records `RAG_RETRIEVAL` with the
   matched sources. On a hit, the passages are appended to the system prompt.
3. `ContextManager` fits the history into the budget. If turns have to be
   dropped it records `CONTEXT_COMPACTION`, summarises them with a real LLM
   call recorded as `SUMMARIZATION`, and records the outcome in
   `CONTEXT_SELECTION`.
4. `LLMProvider` calls the model **with the tool schemas attached** and records
   `LLM_CALL` with tokens, latency and cost.
5. For each tool call the model requests: `TOOL_DECISION` is recorded, the
   `Validator` checks it (`VALIDATION`), and a valid call is executed
   (`TOOL_RESULT`).
6. A failed validation or a failing tool result records `REPLAN`, and the loop
   records `RETRY` and goes back to step 3 with the error in context.
7. When the model answers without requesting tools, `FINAL_RESPONSE` is
   recorded and the run ends.

## Two Independent Limits

The agent loop is bounded twice, because these are different failure modes:

- `AGENT_MAX_RETRIES` (default 3) caps how often the agent may replan after a
  failure.
- `AGENT_MAX_STEPS` (default 8) caps the total number of LLM calls in one
  request, so a model that keeps requesting tools *successfully* still
  terminates.

## Advertised vs. Accepted Tools

`GlassBoxAgent` separates the tools shown to the model (`advertised_tools`)
from the tools it will accept and run (`tools`). They are the same in normal
operation. The Failure Lab advertises an extra `send_email` tool that the
validator does not accept, which is how the wrong-tool path is exercised
deterministically — a well-behaved model will not otherwise invent a tool.
