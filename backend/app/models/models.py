from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
import datetime
from app.database.database import Base

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.datetime.now(IST)

class Run(Base):
    __tablename__ = "runs"

    run_id = Column(String, primary_key=True, index=True)
    conversation_id = Column(String, index=True)
    start_time = Column(DateTime(timezone=True), default=now_ist)
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String)  # RUNNING, SUCCESS, RECOVERED, FAILED, PARTIAL_TRACE
    total_latency_ms = Column(Float, default=0.0)
    total_input_tokens = Column(Integer, default=0)
    total_output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    llm_call_count = Column(Integer, default=0)
    tool_call_count = Column(Integer, default=0)
    validation_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    context_original_tokens = Column(Integer, default=0)
    context_final_tokens = Column(Integer, default=0)
    context_reduction_percentage = Column(Float, default=0.0)

    traces = relationship("TraceStep", back_populates="run", cascade="all, delete-orphan")

class TraceStep(Base):
    __tablename__ = "trace_steps"

    step_id = Column(String, primary_key=True, index=True)
    run_id = Column(String, ForeignKey("runs.run_id"), index=True)
    parent_step_id = Column(String, ForeignKey("trace_steps.step_id"), nullable=True, index=True)
    step_number = Column(Integer)
    timestamp_start = Column(DateTime(timezone=True), default=now_ist)
    timestamp_end = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Float, default=0.0)
    step_type = Column("type", String, index=True) # USER_INPUT, CONTEXT_SELECTION, etc.
    status = Column(String)
    input_data = Column("input", JSON, nullable=True)
    output_data = Column("output", JSON, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    error = Column(JSON, nullable=True)
    model = Column(String, nullable=True)
    token_usage = Column(JSON, nullable=True)
    cost = Column(Float, default=0.0)

    run = relationship("Run", back_populates="traces")
    sub_steps = relationship("TraceStep", backref="parent", remote_side=[step_id])
