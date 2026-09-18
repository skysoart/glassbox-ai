# Architecture

## Components
1. **FastAPI Backend**: Serves API endpoints for traces and chat.
2. **Context Manager**: Orchestrates token reduction and memory selection.
3. **TraceCollector**: Tightly integrated into the agent execution loop, capturing database records natively via SQLAlchemy.
4. **React Frontend**: Reads SQLite Trace database to display real-time dashboard and failure metrics.

## Request Lifecycle
1. User submits request.
2. `USER_INPUT` trace recorded.
3. `ContextManager` shrinks history to fit token budget (`CONTEXT_SELECTION`).
4. `LLMProvider` connects to Gemini API (`LLM_CALL`).
5. If tools are needed, a `TOOL_DECISION` is recorded.
6. The `Validator` intercepts the tool request to verify structure and availability (`VALIDATION`).
7. Result execution is traced, and the agent replans if failures occur (`TOOL_RESULT` / `REPLAN`).
8. The run completes with a `FINAL_RESPONSE`.
