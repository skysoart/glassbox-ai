import json
from typing import Any, Dict, List

from app import config
from app.agent.context_manager import ContextManager
from app.agent.llm_provider import get_provider
from app.agent.tools import TOOLS_SCHEMA, execute_tool, search_docs
from app.agent.validator import Validator
from app.tracing.collector import TraceCollector

SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Use the provided tools when they would give a "
    "more accurate answer than reasoning alone. When a tool result is returned to "
    "you, use it to answer the user's question directly."
)


class GlassBoxAgent:
    def __init__(
        self,
        trace_collector: TraceCollector,
        tools: List[Dict[str, Any]] = None,
        advertised_tools: List[Dict[str, Any]] = None,
        use_rag: bool = True,
    ):
        self.tracer = trace_collector
        self.provider = get_provider()
        self.context_manager = ContextManager()
        # Tools the agent will actually accept and execute.
        self.tools = TOOLS_SCHEMA if tools is None else tools
        # Tools shown to the model. Normally identical, but the diagnostics
        # advertise an extra tool the validator does not accept, which is how
        # the wrong-tool-selection path is exercised on demand.
        self.advertised_tools = self.tools if advertised_tools is None else advertised_tools
        # The diagnostics turn retrieval off: docs/ documents the validator
        # itself, so retrieving it primes the model to refuse a bad tool call
        # instead of making one, and the drill never reaches the validator.
        self.use_rag = use_rag
        self.system_prompt = SYSTEM_PROMPT

    # --- retrieval ----------------------------------------------------------

    def _retrieve(self, user_message: str) -> str:
        """Run the inline RAG pass and return the system prompt to use."""
        if not self.use_rag:
            return self.system_prompt

        rag_text, matched, details = search_docs(user_message)

        self.tracer.add_step(
            step_type="RAG_RETRIEVAL",
            status="SUCCESS",
            input_data={"query": user_message},
            output_data={"matched": matched, "text": rag_text, "details": details},
        )

        if matched:
            return self.system_prompt + "\n\nKnowledge Base Documentation:\n" + rag_text
        return self.system_prompt

    # --- tool handling ------------------------------------------------------

    def _run_tool_calls(self, tool_calls: List[Dict[str, Any]], llm_step_id: str, history: List[Dict[str, Any]]) -> bool:
        """Execute every requested tool call and append the results to history.

        Returns True when at least one call failed validation or execution, so
        the caller knows this round counts as a replan.

        Every tool call gets a response message, including the ones that fail.
        The chat completions API rejects a request where an assistant message
        announces tool calls that are not all answered, so bailing out early
        would poison the next turn.
        """
        needs_replan = False

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            raw_arguments = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_arguments)
                parse_error = None
            except (ValueError, TypeError) as exc:
                args = {}
                parse_error = str(exc)

            self.tracer.add_step(
                step_type="TOOL_DECISION",
                status="SUCCESS",
                input_data={"tool": tool_name, "arguments": args, "raw_arguments": raw_arguments},
                parent_step_id=llm_step_id,
            )

            if parse_error is not None:
                message = "Arguments were not valid JSON: " + parse_error
                self.tracer.add_step(
                    step_type="VALIDATION",
                    status="FAILED",
                    output_data={"message": message},
                    parent_step_id=llm_step_id,
                )
                self._append_tool_result(history, tc, tool_name, "Validation failed: " + message)
                needs_replan = True
                continue

            is_valid, val_msg = Validator.validate_tool_call(tool_name, args, self.tools)
            self.tracer.add_step(
                step_type="VALIDATION",
                status="SUCCESS" if is_valid else "FAILED",
                output_data={"message": val_msg},
                parent_step_id=llm_step_id,
            )

            if not is_valid:
                self.tracer.add_step(step_type="REPLAN", metadata={"reason": val_msg})
                self._append_tool_result(
                    history, tc, tool_name,
                    "Validation failed: " + val_msg + " Please call the tool again with correct arguments.",
                )
                needs_replan = True
                continue

            tool_result = execute_tool(tool_name, args)
            res_valid, res_msg = Validator.validate_tool_result(tool_name, tool_result)

            self.tracer.add_step(
                step_type="TOOL_RESULT",
                status="SUCCESS" if res_valid else "FAILED",
                input_data={"tool": tool_name, "arguments": args},
                output_data={"result": tool_result},
                parent_step_id=llm_step_id,
            )

            self._append_tool_result(history, tc, tool_name, tool_result)

            if not res_valid:
                self.tracer.add_step(step_type="REPLAN", metadata={"reason": res_msg})
                needs_replan = True

        return needs_replan

    @staticmethod
    def _echo_tool_call(tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Rebuild a tool call for the assistant message we send back.

        Any provider-specific extra_content is preserved: Gemini 3.x attaches a
        thought_signature to each tool call and rejects the follow-up request
        with a 400 if it is not echoed back verbatim.
        """
        echoed = {
            "id": tool_call["id"],
            "type": "function",
            "function": {
                "name": tool_call["function"]["name"],
                "arguments": tool_call["function"].get("arguments") or "{}",
            },
        }
        if tool_call.get("extra_content"):
            echoed["extra_content"] = tool_call["extra_content"]
        return echoed

    @staticmethod
    def _append_tool_result(history: List[Dict[str, Any]], tool_call: Dict[str, Any], tool_name: str, content: str):
        history.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "name": tool_name,
            "content": content,
        })

    # --- main loop ----------------------------------------------------------

    def chat(self, user_message: str, history: List[Dict[str, Any]], memories: List[str] = None) -> str:
        self.tracer.add_step(step_type="USER_INPUT", input_data={"message": user_message})

        dynamic_system_prompt = self._retrieve(user_message)
        history.append({"role": "user", "content": user_message})

        max_retries = config.AGENT_MAX_RETRIES
        max_steps = config.AGENT_MAX_STEPS
        retry_count = 0
        step_count = 0

        # Two independent limits: retries bound how often the agent may replan
        # after a failure, and steps bound the total number of LLM calls so a
        # model that keeps requesting tools successfully cannot loop forever.
        while step_count < max_steps and retry_count <= max_retries:
            step_count += 1

            ctx = self.context_manager.build_context(
                dynamic_system_prompt, history, memories, tracer=self.tracer
            )
            self.tracer.add_step(step_type="CONTEXT_SELECTION", metadata=ctx["metadata"])

            llm_result = self.provider.generate(ctx["messages"], tools=self.advertised_tools)

            if llm_result.get("error"):
                self.tracer.add_step(
                    step_type="FAILURE",
                    status="FAILED",
                    error={"message": llm_result["error"]},
                    model=llm_result.get("model"),
                    duration_ms=llm_result.get("duration_ms", 0.0),
                )
                return "SYSTEM ERROR: " + llm_result["error"]

            llm_step = self.tracer.add_step(
                step_type="LLM_CALL",
                output_data={
                    "content": llm_result["content"],
                    "tool_calls": llm_result["tool_calls"],
                },
                token_usage={
                    "prompt_tokens": llm_result["prompt_tokens"],
                    "completion_tokens": llm_result["completion_tokens"],
                },
                cost=llm_result["cost"],
                cost_known=llm_result.get("cost_known", True),
                model=llm_result["model"],
                duration_ms=llm_result["duration_ms"],
            )

            # No tool calls means this is the final answer.
            if not llm_result["tool_calls"]:
                content = llm_result["content"] or ""
                self.tracer.add_step(step_type="FINAL_RESPONSE", output_data={"content": content})
                history.append({"role": "assistant", "content": content})
                return content

            # Record the assistant turn with every tool call it requested,
            # then answer all of them.
            history.append({
                "role": "assistant",
                "content": llm_result.get("content") or None,
                "tool_calls": [self._echo_tool_call(tc) for tc in llm_result["tool_calls"]],
            })

            needs_replan = self._run_tool_calls(llm_result["tool_calls"], llm_step.step_id, history)

            if needs_replan:
                retry_count += 1
                self.tracer.add_step(
                    step_type="RETRY",
                    metadata={"retry_count": retry_count, "max_retries": max_retries},
                )

        reason = (
            "Max retries exceeded." if retry_count > max_retries
            else "Step limit of " + str(max_steps) + " reached without a final answer."
        )
        self.tracer.add_step(
            step_type="FAILURE",
            status="FAILED",
            error={"message": reason},
            metadata={"steps_used": step_count, "retries_used": retry_count},
        )
        return "I'm sorry, I was unable to complete the request. (" + reason + ")"
