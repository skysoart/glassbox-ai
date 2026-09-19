import datetime
import uuid

from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.models import Run, TraceStep

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Step types that advance the per-run counters. Keeping this next to the
# counters makes the previous mismatch (incrementing on "TOOL_CALL", a step
# type the agent never emits) hard to reintroduce.
STEP_COUNTERS = {
    "LLM_CALL": "llm_call_count",
    "SUMMARIZATION": "llm_call_count",
    "TOOL_DECISION": "tool_call_count",
    "VALIDATION": "validation_count",
    "RETRY": "retry_count",
}


def now_ist():
    return datetime.datetime.now(IST)


class TraceCollector:
    def __init__(self, session: Session = None):
        self.session = session or SessionLocal()
        self.current_run = None

    def start_run(self, conversation_id: str) -> Run:
        run_id = str(uuid.uuid4())
        self.current_run = Run(
            run_id=run_id,
            conversation_id=conversation_id,
            status="RUNNING",
            start_time=now_ist(),
        )
        self.session.add(self.current_run)
        self.session.commit()
        self._step_count = 0
        return self.current_run

    def end_run(self, status: str = "SUCCESS"):
        if not self.current_run:
            return None

        self.current_run.status = status
        self.current_run.end_time = now_ist()

        start = self.current_run.start_time
        end = self.current_run.end_time
        if start and end:
            if start.tzinfo is None:
                start = start.replace(tzinfo=IST)
            if end.tzinfo is None:
                end = end.replace(tzinfo=IST)
            self.current_run.total_latency_ms = (end - start).total_seconds() * 1000.0

        self.session.commit()
        return self.current_run

    def _next_step_number(self) -> int:
        """Step numbers are sequential within a run.

        Counted in memory rather than with a COUNT(*) per step, which was one
        query per trace entry.
        """
        if not hasattr(self, "_step_count") or self._step_count is None:
            self._step_count = (
                self.session.query(TraceStep)
                .filter(TraceStep.run_id == self.current_run.run_id)
                .count()
            )
        self._step_count += 1
        return self._step_count

    def add_step(
        self,
        step_type: str,
        status: str = "SUCCESS",
        parent_step_id: str = None,
        input_data: dict = None,
        output_data: dict = None,
        metadata: dict = None,
        error: dict = None,
        model: str = None,
        token_usage: dict = None,
        cost: float = 0.0,
        cost_known: bool = True,
        duration_ms: float = 0.0,
    ) -> TraceStep:
        if not self.current_run:
            raise ValueError("No active run. Call start_run first.")

        started_at = now_ist()
        step = TraceStep(
            step_id=str(uuid.uuid4()),
            run_id=self.current_run.run_id,
            parent_step_id=parent_step_id,
            step_number=self._next_step_number(),
            step_type=step_type,
            status=status,
            input_data=input_data,
            output_data=output_data,
            metadata_json=metadata,
            error=error,
            model=model,
            token_usage=token_usage,
            cost=cost or 0.0,
            cost_known=cost_known,
            duration_ms=duration_ms,
            timestamp_start=started_at,
            timestamp_end=started_at,
        )
        self.session.add(step)

        counter = STEP_COUNTERS.get(step_type)
        if counter:
            setattr(self.current_run, counter, (getattr(self.current_run, counter) or 0) + 1)

        if status == "FAILED":
            self.current_run.failure_count = (self.current_run.failure_count or 0) + 1

        if token_usage:
            in_t = token_usage.get("prompt_tokens", 0) or 0
            out_t = token_usage.get("completion_tokens", 0) or 0
            self.current_run.total_input_tokens = (self.current_run.total_input_tokens or 0) + in_t
            self.current_run.total_output_tokens = (self.current_run.total_output_tokens or 0) + out_t
            self.current_run.total_tokens = (self.current_run.total_tokens or 0) + in_t + out_t

        self.current_run.total_cost = (self.current_run.total_cost or 0.0) + (cost or 0.0)
        # One unpriced call makes the whole run total a lower bound.
        if not cost_known and token_usage:
            self.current_run.cost_known = False

        # Mirror the latest context figures onto the run so the runs list can
        # show them without loading every step.
        if step_type == "CONTEXT_SELECTION" and metadata:
            self.current_run.context_original_tokens = metadata.get("original_tokens", 0)
            self.current_run.context_final_tokens = metadata.get("final_tokens", 0)
            self.current_run.context_reduction_percentage = metadata.get("reduction_percentage", 0.0)

        self.session.commit()
        return step
