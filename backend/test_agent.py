import os
import sys

# Ensure app path is available
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.database import SessionLocal, Base, engine
from app.tracing.collector import TraceCollector
from app.agent.agent import GlassBoxAgent

from dotenv import load_dotenv
load_dotenv()

def main():
    Base.metadata.create_all(bind=engine)
    
    session = SessionLocal()
    tracer = TraceCollector(session=session)
    agent = GlassBoxAgent(tracer)
    
    conversation_id = "test_cli_convo_01"
    run = tracer.start_run(conversation_id)
    
    history = []
    
    # Test a simple query
    print("User: What is 25 * 4?")
    response = agent.chat("What is 25 * 4?", history)
    print(f"Agent: {response}")
    
    tracer.end_run("SUCCESS")
    session.refresh(run)
    
    print("\n--- Trace Summary ---")
    print(f"Run Status: {run.status}")
    print(f"Total tokens: {run.total_tokens}")
    print(f"Tool calls: {run.tool_call_count}")
    print(f"Total cost: ${run.total_cost:.6f}")
    
    print("\nTrace Steps:")
    # We sort by step_number just in case
    sorted_traces = sorted(run.traces, key=lambda x: x.step_number)
    for step in sorted_traces:
        print(f"- Step {step.step_number}: {step.step_type} ({step.status})")
        if step.status == "FAILED" and step.error:
            print(f"  Error details: {step.error}")
        
if __name__ == "__main__":
    main()
