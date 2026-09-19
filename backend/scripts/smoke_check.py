"""Manual end-to-end check against the live LLM API.

This is NOT part of the test suite: it needs a working LLM_API_KEY and it
spends real credit. The automated tests live in backend/tests/ and run offline.

    python scripts/smoke_check.py
    python scripts/smoke_check.py "What is 25 * 4?"
"""
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import config  # noqa: E402  (must precede anything reading env vars)
from app.agent.agent import GlassBoxAgent  # noqa: E402
from app.database.database import SessionLocal, ensure_schema  # noqa: E402
from app.tracing.collector import TraceCollector  # noqa: E402


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "What is 25 * 4?"

    if not config.LLM_API_KEY:
        print("LLM_API_KEY is not set. Copy .env.example to .env and add your key.")
        return 1

    ensure_schema()
    session = SessionLocal()
    tracer = TraceCollector(session=session)
    run = tracer.start_run("smoke_check")

    print("Model:    " + config.LLM_MODEL + " (" + config.LLM_PROVIDER + ")")
    print("Budget:   " + str(config.CONTEXT_MAX_TOKENS) + " tokens")
    print("User:     " + question)

    agent = GlassBoxAgent(trace_collector=tracer)
    answer = agent.chat(question, [])
    print("Agent:    " + str(answer))

    status = "RECOVERED" if (run.failure_count or 0) else "SUCCESS"
    tracer.end_run(status)
    session.refresh(run)

    cost = ("$" + format(run.total_cost, ".6f")) if run.cost_known else "unknown (model not priced)"
    print("\n--- Trace Summary ---")
    print("Run id:      " + run.run_id)
    print("Status:      " + str(run.status))
    print("Latency:     " + format(run.total_latency_ms or 0.0, ".0f") + " ms")
    print("Tokens:      " + str(run.total_tokens) + " (in " + str(run.total_input_tokens)
          + " / out " + str(run.total_output_tokens) + ")")
    print("LLM calls:   " + str(run.llm_call_count))
    print("Tool calls:  " + str(run.tool_call_count))
    print("Validations: " + str(run.validation_count))
    print("Retries:     " + str(run.retry_count))
    print("Cost:        " + cost)

    print("\nSteps:")
    for step in sorted(run.traces, key=lambda s: s.step_number):
        line = "  " + str(step.step_number).rjust(2) + ". " + step.step_type + " (" + str(step.status) + ")"
        print(line)
        if step.status == "FAILED" and step.error:
            print("      error: " + str(step.error))

    session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
