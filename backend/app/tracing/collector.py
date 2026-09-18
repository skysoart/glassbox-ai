import uuid
import datetime
from sqlalchemy.orm import Session
from app.models.models import Run, TraceStep
from app.database.database import SessionLocal

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

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
            status="RUNNING"
        )
        self.session.add(self.current_run)
        self.session.commit()
        return self.current_run

    def end_run(self, status: str = "SUCCESS"):
        if self.current_run:
            self.current_run.status = status
            self.current_run.end_time = now_ist()
            
            # calculate total latency
            if self.current_run.start_time and self.current_run.end_time:
                start = self.current_run.start_time
                if start.tzinfo is None:
                    start = start.replace(tzinfo=IST)
                end = self.current_run.end_time
                if end.tzinfo is None:
                    end = end.replace(tzinfo=IST)
                delta = end - start
                self.current_run.total_latency_ms = delta.total_seconds() * 1000.0

            self.session.commit()
            return self.current_run
        return None

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
        duration_ms: float = 0.0
    ) -> TraceStep:
        if not self.current_run:
            raise ValueError("No active run. Call start_run first.")
        
        # Determine step number for this run
        step_number = self.session.query(TraceStep).filter(TraceStep.run_id == self.current_run.run_id).count() + 1

        step = TraceStep(
            step_id=str(uuid.uuid4()),
            run_id=self.current_run.run_id,
            parent_step_id=parent_step_id,
            step_number=step_number,
            step_type=step_type,
            status=status,
            input_data=input_data,
            output_data=output_data,
            metadata_json=metadata,
            error=error,
            model=model,
            token_usage=token_usage,
            cost=cost,
            duration_ms=duration_ms,
            timestamp_end=now_ist()
        )
        self.session.add(step)
        
        # update run aggregates
        if step_type == "LLM_CALL":
            self.current_run.llm_call_count += 1
        elif step_type == "TOOL_CALL":
            self.current_run.tool_call_count += 1
        
        if token_usage:
            in_t = token_usage.get("prompt_tokens", 0)
            out_t = token_usage.get("completion_tokens", 0)
            self.current_run.total_input_tokens += in_t
            self.current_run.total_output_tokens += out_t
            self.current_run.total_tokens += (in_t + out_t)
            
        self.current_run.total_cost += cost

        self.session.commit()
        return step
