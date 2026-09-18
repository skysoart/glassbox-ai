from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.database.database import engine, Base, get_db
from app.models.models import Run, TraceStep
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="GlassBox AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

class StartRunRequest(BaseModel):
    conversation_id: str

@app.post("/api/runs")
def create_run(request: StartRunRequest, db: Session = Depends(get_db)):
    from app.tracing.collector import TraceCollector
    collector = TraceCollector(session=db)
    run = collector.start_run(request.conversation_id)
    return {"run_id": run.run_id, "status": run.status}

@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(Run).order_by(Run.start_time.desc()).all()
    return runs

@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

@app.get("/api/runs/{run_id}/traces")
def get_run_traces(run_id: str, db: Session = Depends(get_db)):
    traces = db.query(TraceStep).filter(TraceStep.run_id == run_id).order_by(TraceStep.step_number).all()
    return traces

@app.get("/api/conversations")
def list_conversations(db: Session = Depends(get_db)):
    from sqlalchemy import func
    result = db.query(
        Run.conversation_id, 
        func.max(Run.start_time).label('last_activity')
    ).filter(Run.conversation_id.like('chat_ui_%')).group_by(Run.conversation_id).order_by(func.max(Run.start_time).desc()).all()
    
    return [{"conversation_id": r[0], "last_activity": r[1]} for r in result]

@app.get("/api/conversations/{conversation_id}/history")
def get_conversation_history(conversation_id: str, db: Session = Depends(get_db)):
    runs = db.query(Run).filter(Run.conversation_id == conversation_id).order_by(Run.start_time.asc()).all()
    
    history = []
    for run in runs:
        traces = db.query(TraceStep).filter(TraceStep.run_id == run.run_id).order_by(TraceStep.step_number.asc()).all()
        user_msg = None
        assistant_msg = None
        for trace in traces:
            if trace.step_type == "USER_INPUT" and trace.input_data:
                user_msg = trace.input_data.get("message")
            elif trace.step_type == "FINAL_RESPONSE" and trace.output_data:
                assistant_msg = trace.output_data.get("content")
        
        if user_msg:
            history.append({"role": "user", "content": user_msg, "run_id": run.run_id})
        if assistant_msg:
            history.append({"role": "assistant", "content": assistant_msg, "run_id": run.run_id})
            
    return {"conversation_id": conversation_id, "history": history}

class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    history: List[Dict[str, Any]] = []

@app.post("/api/chat")
def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    from app.tracing.collector import TraceCollector
    from app.agent.agent import GlassBoxAgent
    
    collector = TraceCollector(session=db)
    run = collector.start_run(request.conversation_id)
    
    try:
        agent = GlassBoxAgent(trace_collector=collector)
        response = agent.chat(request.message, request.history)
        collector.end_run("SUCCESS")
        return {
            "run_id": run.run_id,
            "response": response,
            "history": request.history
        }
    except Exception as e:
        collector.end_run("FAILED")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tests/failure-wrong-tool")
def trigger_wrong_tool(db: Session = Depends(get_db)):
    """Forces the agent to use a wrong tool and recover"""
    from app.tracing.collector import TraceCollector
    from app.agent.agent import GlassBoxAgent
    collector = TraceCollector(session=db)
    run = collector.start_run("test_wrong_tool")
    
    agent = GlassBoxAgent(trace_collector=collector)
    # The agent will try to answer this. To force a wrong tool, we can simulate an injection or just ask it to use a tool that doesn't exist.
    # We will just pass a prompt that strongly asks to use a 'send_email' tool which doesn't exist.
    try:
        response = agent.chat("Please use the 'send_email' tool to email my results.", [])
        collector.end_run("SUCCESS")
        return {"run_id": run.run_id, "response": response}
    except Exception as e:
        collector.end_run("FAILED")
        return {"run_id": run.run_id, "error": str(e)}

@app.post("/api/tests/stress-test")
def trigger_stress_test(db: Session = Depends(get_db)):
    """Runs a 20+ turn stress test to demonstrate context retention"""
    from app.tracing.collector import TraceCollector
    from app.agent.agent import GlassBoxAgent
    collector = TraceCollector(session=db)
    run = collector.start_run("test_stress_20_turns")
    
    agent = GlassBoxAgent(trace_collector=collector)
    history = []
    memories = ["The secret project code is 'OMEGA-99'."]
    
    try:
        # We will simulate 20 turns of chatter
        for i in range(20):
            history.append({"role": "user", "content": f"Turn {i}: Can you tell me a random fun fact?"})
            history.append({"role": "assistant", "content": f"Fact {i}: The sky is blue."})
            
        # 21st turn asks about the memory
        response = agent.chat("What is the secret project code I told you about?", history, memories=memories)
        collector.end_run("SUCCESS")
        return {"run_id": run.run_id, "response": response}
    except Exception as e:
        collector.end_run("FAILED")
        return {"run_id": run.run_id, "error": str(e)}
