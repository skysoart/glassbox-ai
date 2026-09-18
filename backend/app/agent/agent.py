import json
from app.tracing.collector import TraceCollector
from app.agent.llm_provider import get_provider
from app.agent.context_manager import ContextManager
from app.agent.tools import execute_tool, TOOLS_SCHEMA
from app.agent.validator import Validator

class GlassBoxAgent:
    def __init__(self, trace_collector: TraceCollector):
        self.tracer = trace_collector
        self.provider = get_provider()
        self.context_manager = ContextManager()
        self.system_prompt = "You are a helpful AI assistant. Use tools when necessary."
        
    def chat(self, user_message: str, history: list, memories: list = None) -> str:
        # Trace input
        self.tracer.add_step(
            step_type="USER_INPUT",
            input_data={"message": user_message}
        )
        
        # Execute RAG Pipeline
        from app.agent.tools import file_search
        rag_result = file_search(user_message)
        
        self.tracer.add_step(
            step_type="RAG_RETRIEVAL",
            input_data={"query": user_message},
            output_data=rag_result
        )
        
        dynamic_system_prompt = self.system_prompt + "\n\nKnowledge Base Results:\n" + rag_result
        
        history.append({"role": "user", "content": user_message})

        # Max retries for replanning (e.g. wrong tool)
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            # Context selection
            ctx = self.context_manager.build_context(dynamic_system_prompt, history, memories, tracer=self.tracer)
            ctx_step = self.tracer.add_step(
                step_type="CONTEXT_SELECTION",
                metadata=ctx["metadata"]
            )
            
            # LLM Call
            llm_result = self.provider.generate(ctx["messages"])
            
            if llm_result.get("error"):
                self.tracer.add_step(
                    step_type="FAILURE",
                    status="FAILED",
                    error={"message": llm_result["error"]},
                    model=llm_result["model"],
                    duration_ms=llm_result["duration_ms"]
                )
                return f"SYSTEM ERROR: {llm_result['error']}"

            llm_step = self.tracer.add_step(
                step_type="LLM_CALL",
                output_data={"content": llm_result["content"], "tool_calls": llm_result["tool_calls"]},
                token_usage={"prompt_tokens": llm_result["prompt_tokens"], "completion_tokens": llm_result["completion_tokens"]},
                cost=llm_result["cost"],
                model=llm_result["model"],
                duration_ms=llm_result["duration_ms"]
            )

            # If no tools called, we have a final response
            if not llm_result["tool_calls"]:
                self.tracer.add_step(
                    step_type="FINAL_RESPONSE",
                    output_data={"content": llm_result["content"]}
                )
                history.append({"role": "assistant", "content": llm_result["content"]})
                return llm_result.get("content", "")
            
            # Tool handling
            assistant_msg = {"role": "assistant", "content": llm_result.get("content"), "tool_calls": []}
            history.append(assistant_msg)
            
            needs_replan = False
            for tc in llm_result["tool_calls"]:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except:
                    args = {}

                # Trace tool decision
                self.tracer.add_step(
                    step_type="TOOL_DECISION",
                    input_data={"tool": tool_name, "arguments": args},
                    parent_step_id=llm_step.step_id
                )

                # Validate Tool Call
                is_valid, val_msg = Validator.validate_tool_call(tool_name, args, TOOLS_SCHEMA)
                self.tracer.add_step(
                    step_type="VALIDATION",
                    status="SUCCESS" if is_valid else "FAILED",
                    output_data={"message": val_msg},
                    parent_step_id=llm_step.step_id
                )

                if not is_valid:
                    self.tracer.add_step(step_type="REPLAN", metadata={"reason": val_msg})
                    # Use role "tool" with error message for validation failures to satisfy OpenAI schema
                    history.append({
                        "role": "tool", 
                        "tool_call_id": tc["id"],
                        "name": tool_name,
                        "content": f"Validation failed: {val_msg}. Please replan and use the correct arguments."
                    })
                    assistant_msg["tool_calls"].append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tool_name, "arguments": tc["function"]["arguments"]}
                    })
                    needs_replan = True
                    break

                # Execute Tool
                tool_result = execute_tool(tool_name, args)
                
                # Validate Tool Result
                res_valid, res_msg = Validator.validate_tool_result(tool_name, tool_result)
                
                self.tracer.add_step(
                    step_type="TOOL_RESULT",
                    input_data={"tool": tool_name},
                    output_data={"result": tool_result},
                    status="SUCCESS" if res_valid else "FAILED",
                    parent_step_id=llm_step.step_id
                )
                
                assistant_msg["tool_calls"].append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tool_name, "arguments": tc["function"]["arguments"]}
                })
                history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tool_name,
                    "content": tool_result
                })
                
                if not res_valid:
                    self.tracer.add_step(step_type="REPLAN", metadata={"reason": res_msg})
                    needs_replan = True
                    break

            if needs_replan:
                retry_count += 1
                self.tracer.add_step(step_type="RETRY", metadata={"retry_count": retry_count})
                if self.tracer.current_run:
                    self.tracer.current_run.retry_count += 1
                    self.tracer.current_run.failure_count += 1
                continue
            
            # Loop back to generate the next step with the tool outputs

        self.tracer.add_step(step_type="FAILURE", status="FAILED", error={"message": "Max retries exceeded."})
        return "I'm sorry, I was unable to complete the request."
