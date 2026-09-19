# Demo Script

1. **Start the system.** Run the FastAPI backend and the Vite frontend (see the
   README). `GET /health` reports the model, provider and token budget in use.
2. **Normal chat with a tool call.** Ask "What is 4871 * 392?". The trace shows
   `TOOL_DECISION` → `VALIDATION` → `TOOL_RESULT`, then a second `LLM_CALL`
   that turns the tool output into the answer.
3. **Cost view.** Open Cost & Token Analysis for the per-model breakdown. If
   your model has no configured price the page says so explicitly and marks the
   totals as a lower bound rather than showing $0.00.
4. **Context inspector.** Open a run and expand `CONTEXT_SELECTION` to see the
   budget, the tokens before and after, the measured reduction, and which turns
   and memories were retained.
5. **Failure Lab — Wrong Tool.** The agent is offered a `send_email` tool that
   the validator does not accept. Watch `VALIDATION` fail, `REPLAN` and `RETRY`
   fire, and the agent recover by answering with the tools it does have. The
   response reports `validation_failures` and `retries`; the run is marked
   `RECOVERED`, not `SUCCESS`.
6. **Failure Lab — Stress Test.** Twenty padded turns exceed the 8k budget, so
   `CONTEXT_COMPACTION` and `SUMMARIZATION` fire and roughly 14% of the context
   is reclaimed. The agent still recalls the injected memory (`OMEGA-99`),
   because memories are placed next to the current turn rather than at the top
   of the prompt.
7. **Export.** Use **Export Log** on any run to download the full
   `glassbox.trace.v1` JSON document.
