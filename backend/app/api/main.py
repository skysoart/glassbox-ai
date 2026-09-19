from typing import Any, Dict, List, Optional

# config must be imported before anything that reads environment variables at
# import time (app.database.database does), because it is what loads .env.
from app import config  # noqa: I001

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.database import ensure_schema, get_db
from app.models.models import Run, TraceStep

ensure_schema()

app = FastAPI(title="GlassBox AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    # Credentials cannot be combined with a wildcard origin; browsers reject it.
    allow_credentials="*" not in config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- serialization ----------------------------------------------------------

def run_to_dict(run: Run) -> Dict[str, Any]:
    return {
        "run_id": run.run_id,
        "conversation_id": run.conversation_id,
        "start_time": run.start_time,
        "end_time": run.end_time,
        "status": run.status,
        "total_latency_ms": run.total_latency_ms,
        "total_input_tokens": run.total_input_tokens,
        "total_output_tokens": run.total_output_tokens,
        "total_tokens": run.total_tokens,
        "total_cost": run.total_cost,
        "cost_known": bool(run.cost_known) if run.cost_known is not None else True,
        "llm_call_count": run.llm_call_count,
        "tool_call_count": run.tool_call_count,
        "validation_count": run.validation_count,
        "failure_count": run.failure_count,
        "retry_count": run.retry_count,
        "context_original_tokens": run.context_original_tokens,
        "context_final_tokens": run.context_final_tokens,
        "context_reduction_percentage": run.context_reduction_percentage,
    }


def step_to_dict(step: TraceStep) -> Dict[str, Any]:
    return {
        "step_id": step.step_id,
        "run_id": step.run_id,
        "parent_step_id": step.parent_step_id,
        "step_number": step.step_number,
        "timestamp_start": step.timestamp_start,
        "timestamp_end": step.timestamp_end,
        "duration_ms": step.duration_ms,
        "step_type": step.step_type,
        "status": step.status,
        "input_data": step.input_data,
        "output_data": step.output_data,
        "metadata_json": step.metadata_json,
        "error": step.error,
        "model": step.model,
        "token_usage": step.token_usage,
        "cost": step.cost,
        "cost_known": bool(step.cost_known) if step.cost_known is not None else True,
    }


# --- health -----------------------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "provider": config.LLM_PROVIDER,
        "model": config.LLM_MODEL,
        "context_budget_tokens": config.CONTEXT_MAX_TOKENS,
        "test_endpoints_enabled": config.ENABLE_TEST_ENDPOINTS,
    }


# --- runs -------------------------------------------------------------------

class StartRunRequest(BaseModel):
    conversation_id: str


@app.post("/api/runs")
def create_run(request: StartRunRequest, db: Session = Depends(get_db)):
    from app.tracing.collector import TraceCollector

    collector = TraceCollector(session=db)
    run = collector.start_run(request.conversation_id)
    return {"run_id": run.run_id, "status": run.status}


@app.get("/api/runs")
def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Most recent runs first. Paginated so the list cannot grow unbounded."""
    runs = (
        db.query(Run)
        .order_by(Run.start_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [run_to_dict(r) for r in runs]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_to_dict(run)


@app.get("/api/runs/{run_id}/traces")
def get_run_traces(run_id: str, db: Session = Depends(get_db)):
    steps = (
        db.query(TraceStep)
        .filter(TraceStep.run_id == run_id)
        .order_by(TraceStep.step_number)
        .all()
    )
    return [step_to_dict(s) for s in steps]


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: str, db: Session = Depends(get_db)):
    """Download a run and its full trace as a single JSON document."""
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = (
        db.query(TraceStep)
        .filter(TraceStep.run_id == run_id)
        .order_by(TraceStep.step_number)
        .all()
    )

    payload = {
        "format": "glassbox.trace.v1",
        "run": run_to_dict(run),
        "steps": [step_to_dict(s) for s in steps],
    }
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Content-Disposition": 'attachment; filename="glassbox-run-' + run_id + '.json"'},
    )


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str, db: Session = Depends(get_db)):
    """Delete a run and its trace steps.

    The runs table had a Delete button that only removed the row from local
    React state, so the run reappeared on the next reload.
    """
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    db.delete(run)  # trace steps go with it via cascade
    db.commit()
    return {"deleted": run_id}


# --- statistics -------------------------------------------------------------

@app.get("/api/stats/models")
def model_breakdown(db: Session = Depends(get_db)):
    """Per-model token and cost totals, aggregated in SQL.

    The cost page used to render a single hardcoded model name with every
    token attributed to it.
    """
    rows = (
        db.query(
            TraceStep.model,
            func.count(TraceStep.step_id).label("calls"),
            func.sum(TraceStep.cost).label("cost"),
            func.min(TraceStep.cost_known).label("cost_known"),
        )
        .filter(TraceStep.model.isnot(None))
        .group_by(TraceStep.model)
        .order_by(func.sum(TraceStep.cost).desc())
        .all()
    )

    # token_usage is a JSON blob, so the token totals are summed in Python.
    tokens: Dict[str, Dict[str, int]] = {}
    for model, usage in (
        db.query(TraceStep.model, TraceStep.token_usage)
        .filter(TraceStep.model.isnot(None))
        .filter(TraceStep.token_usage.isnot(None))
        .all()
    ):
        bucket = tokens.setdefault(model, {"input": 0, "output": 0})
        if isinstance(usage, dict):
            bucket["input"] += usage.get("prompt_tokens", 0) or 0
            bucket["output"] += usage.get("completion_tokens", 0) or 0

    return [
        {
            "model": row.model,
            "calls": row.calls,
            "cost": row.cost or 0.0,
            "cost_known": bool(row.cost_known) if row.cost_known is not None else True,
            "input_tokens": tokens.get(row.model, {}).get("input", 0),
            "output_tokens": tokens.get(row.model, {}).get("output", 0),
        }
        for row in rows
    ]


# --- conversations ----------------------------------------------------------

@app.get("/api/conversations")
def list_conversations(db: Session = Depends(get_db)):
    rows = (
        db.query(Run.conversation_id, func.max(Run.start_time).label("last_activity"))
        .filter(Run.conversation_id.like("chat_ui_%"))
        .group_by(Run.conversation_id)
        .order_by(func.max(Run.start_time).desc())
        .all()
    )
    return [{"conversation_id": r[0], "last_activity": r[1]} for r in rows]


@app.get("/api/conversations/{conversation_id}/history")
def get_conversation_history(conversation_id: str, db: Session = Depends(get_db)):
    runs = (
        db.query(Run)
        .filter(Run.conversation_id == conversation_id)
        .order_by(Run.start_time.asc())
        .all()
    )
    run_ids = [r.run_id for r in runs]

    # One query for every step instead of one query per run.
    steps_by_run: Dict[str, List[TraceStep]] = {rid: [] for rid in run_ids}
    if run_ids:
        all_steps = (
            db.query(TraceStep)
            .filter(TraceStep.run_id.in_(run_ids))
            .filter(TraceStep.step_type.in_(["USER_INPUT", "FINAL_RESPONSE"]))
            .order_by(TraceStep.step_number.asc())
            .all()
        )
        for step in all_steps:
            steps_by_run.setdefault(step.run_id, []).append(step)

    history = []
    for run in runs:
        user_msg = None
        assistant_msg = None
        for step in steps_by_run.get(run.run_id, []):
            if step.step_type == "USER_INPUT" and step.input_data:
                user_msg = step.input_data.get("message")
            elif step.step_type == "FINAL_RESPONSE" and step.output_data:
                assistant_msg = step.output_data.get("content")

        if user_msg:
            history.append({"role": "user", "content": user_msg, "run_id": run.run_id})
        if assistant_msg:
            history.append({"role": "assistant", "content": assistant_msg, "run_id": run.run_id})

    return {"conversation_id": conversation_id, "history": history}


# --- chat -------------------------------------------------------------------

class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    history: List[Dict[str, Any]] = []
    memories: Optional[List[str]] = None


def _final_status(run: Run) -> str:
    """A run that hit failures but still answered is RECOVERED, not SUCCESS."""
    if (run.failure_count or 0) > 0 or (run.retry_count or 0) > 0:
        return "RECOVERED"
    return "SUCCESS"


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    from app.agent.agent import GlassBoxAgent
    from app.tracing.collector import TraceCollector

    collector = TraceCollector(session=db)
    run = collector.start_run(request.conversation_id)

    try:
        agent = GlassBoxAgent(trace_collector=collector)
        response = agent.chat(request.message, request.history, memories=request.memories)
    except Exception as exc:  # noqa: BLE001 - recorded in the trace before re-raising
        collector.add_step(
            step_type="FAILURE",
            status="FAILED",
            error={"message": str(exc), "type": type(exc).__name__},
        )
        collector.end_run("FAILED")
        raise HTTPException(status_code=500, detail=str(exc))

    collector.end_run(_final_status(run))
    return {
        "run_id": run.run_id,
        "response": response,
        "history": request.history,
    }


# --- diagnostics ------------------------------------------------------------

def _require_test_endpoints():
    if not config.ENABLE_TEST_ENDPOINTS:
        raise HTTPException(
            status_code=403,
            detail="Test endpoints are disabled. Set ENABLE_TEST_ENDPOINTS=true to enable them.",
        )


# Advertised to the model but deliberately absent from the agent's accepted
# tool list, so selecting it is guaranteed to fail validation. Simply asking
# for a tool that was never advertised does not work: a well-behaved model
# just replies that it has no such tool, and the validator never runs.
PHANTOM_TOOL = {
    "type": "function",
    "function": {
        "name": "send_email",
        "description": "Sends an email to a recipient.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient address"},
                "body": {"type": "string", "description": "Message body"},
            },
            "required": ["to", "body"],
        },
    },
}


@app.post("/api/tests/failure-wrong-tool")
def trigger_wrong_tool(db: Session = Depends(get_db)):
    """Drive the validator's wrong-tool-selection path and watch it recover."""
    _require_test_endpoints()
    from app.agent.agent import GlassBoxAgent
    from app.agent.tools import TOOLS_SCHEMA
    from app.tracing.collector import TraceCollector

    collector = TraceCollector(session=db)
    run = collector.start_run("test_wrong_tool")

    try:
        agent = GlassBoxAgent(
            trace_collector=collector,
            tools=TOOLS_SCHEMA,
            advertised_tools=TOOLS_SCHEMA + [PHANTOM_TOOL],
            use_rag=False,
        )
        response = agent.chat(
            "Email the results of 12 * 12 to test@example.com using the send_email tool.",
            [],
        )
        collector.end_run(_final_status(run))
        return {
            "run_id": run.run_id,
            "response": response,
            "validation_failures": run.failure_count,
            "retries": run.retry_count,
        }
    except Exception as exc:  # noqa: BLE001
        collector.end_run("FAILED")
        return {"run_id": run.run_id, "error": str(exc)}


@app.post("/api/tests/stress-test")
def trigger_stress_test(db: Session = Depends(get_db)):
    """Bury a fact under enough turns to force compaction, then ask for it back."""
    _require_test_endpoints()
    from app.agent.agent import GlassBoxAgent
    from app.tracing.collector import TraceCollector

    collector = TraceCollector(session=db)
    run = collector.start_run("test_stress_20_turns")

    memories = ["The secret project code is 'OMEGA-99'."]
    history: List[Dict[str, Any]] = []
    # Padded turns: with an 8k budget these actually exceed the window, which
    # is what makes the compaction step worth watching.
    filler = "Here is a long fun fact. " * 60
    for i in range(20):
        history.append({"role": "user", "content": "Turn " + str(i) + ": tell me a random fun fact."})
        history.append({"role": "assistant", "content": "Fact " + str(i) + ": " + filler})

    try:
        agent = GlassBoxAgent(trace_collector=collector)
        response = agent.chat(
            "What is the secret project code I told you about?", history, memories=memories
        )
        collector.end_run(_final_status(run))
        return {
            "run_id": run.run_id,
            "response": response,
            "context_reduction_percentage": run.context_reduction_percentage,
        }
    except Exception as exc:  # noqa: BLE001
        collector.end_run("FAILED")
        return {"run_id": run.run_id, "error": str(exc)}
