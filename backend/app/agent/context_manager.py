from typing import Any, Dict, List

from app import config
from app.agent.llm_provider import get_provider

try:
    import tiktoken
except ImportError:  # pragma: no cover - tiktoken is a hard dependency in practice
    tiktoken = None

# Rough per-message overhead for role/name/delimiter tokens.
_MESSAGE_OVERHEAD_TOKENS = 4


class ContextManager:
    def __init__(self, max_tokens: int = None):
        # Budget comes from config so it can be tuned per deployment. The old
        # default of 500_000 meant compaction could never trigger.
        self.max_tokens = max_tokens if max_tokens is not None else config.CONTEXT_MAX_TOKENS
        self.provider = get_provider()
        self.encoder = None
        if tiktoken is not None:
            try:
                self.encoder = tiktoken.get_encoding("cl100k_base")
            except Exception:  # noqa: BLE001 - falls back to the estimate below
                self.encoder = None

    def count_tokens(self, text: Any) -> int:
        if text is None:
            return 0
        if not isinstance(text, str):
            text = str(text)
        if self.encoder:
            return len(self.encoder.encode(text))
        return len(text) // 4  # rough fallback

    def count_message_tokens(self, message: Dict[str, Any]) -> int:
        """Token cost of a single message, including its tool call payloads."""
        total = self.count_tokens(message.get("content"))
        if message.get("tool_calls"):
            total += self.count_tokens(message["tool_calls"])
        if message.get("name"):
            total += self.count_tokens(message["name"])
        return total + _MESSAGE_OVERHEAD_TOKENS

    def summarize(self, text_to_summarize: str, tracer=None) -> str:
        """Compress dropped turns into a short summary.

        This is a real LLM call, so it is traced and billed like any other.
        """
        prompt = (
            "Summarize the following conversation history concisely, retaining all "
            "important facts, decisions and context:\n\n" + text_to_summarize
        )
        result = self.provider.generate([{"role": "user", "content": prompt}])

        if tracer:
            tracer.add_step(
                step_type="SUMMARIZATION",
                status="FAILED" if result.get("error") else "SUCCESS",
                input_data={"characters": len(text_to_summarize)},
                output_data={"summary": result.get("content", "")},
                error={"message": result["error"]} if result.get("error") else None,
                model=result.get("model"),
                token_usage={
                    "prompt_tokens": result.get("prompt_tokens", 0),
                    "completion_tokens": result.get("completion_tokens", 0),
                },
                cost=result.get("cost", 0.0),
                cost_known=result.get("cost_known", False),
                duration_ms=result.get("duration_ms", 0.0),
            )

        if result.get("error"):
            # Degrade gracefully: the turns are already dropped, so say so
            # rather than pretending we have a summary.
            return "(Earlier turns were dropped to fit the context budget; summarization failed.)"
        return result.get("content") or "(No summary produced.)"

    @staticmethod
    def _strip_orphan_tool_messages(retained: List[Dict[str, Any]]):
        """Drop leading tool results whose assistant tool_calls message was cut.

        A ``role: "tool"`` message without the preceding assistant message that
        requested it is rejected by the chat completions API, so trimming
        history in the middle of a tool exchange would 400 the next request.
        """
        orphans = []
        while retained and retained[0].get("role") == "tool":
            orphans.append(retained.pop(0))
        return orphans

    def build_context(
        self,
        system_prompt: str,
        history: List[Dict[str, Any]],
        memories: List[str] = None,
        tracer=None,
    ) -> Dict[str, Any]:
        """Build a message list that fits the token budget.

        Returns the finalized messages array plus metadata describing what was
        kept, what was dropped, and how much the context shrank.
        """
        # Measure before any mutation, so the reduction figure is meaningful.
        original_tokens = self.count_tokens(system_prompt) + sum(
            self.count_message_tokens(m) for m in history
        )

        messages = [{"role": "system", "content": system_prompt}]
        current_tokens = self.count_tokens(system_prompt)

        retained_memories = []
        memory_message = None
        if memories:
            # Framed explicitly as established conversation history. Labelled
            # only "Important Facts:", models treated the block as unrelated
            # boilerplate and denied knowing facts that were right in front
            # of them.
            memory_text = (
                "Established facts from earlier in this conversation. The user has "
                "already told you these, so treat them as known and answer from them "
                "directly rather than saying they were never mentioned:\n"
                + "\n".join("- " + m for m in memories)
            )
            mem_tokens = self.count_tokens(memory_text)
            # Memories may claim at most half the budget.
            if current_tokens + mem_tokens < self.max_tokens / 2:
                memory_message = {"role": "system", "content": memory_text}
                current_tokens += mem_tokens
                retained_memories = list(memories)
                original_tokens += mem_tokens

        retained_history: List[Dict[str, Any]] = []
        discarded_history: List[Dict[str, Any]] = []

        # Walk backwards so the most recent turns survive.
        for turn in reversed(history):
            turn_tokens = self.count_message_tokens(turn)
            if current_tokens + turn_tokens <= self.max_tokens:
                retained_history.insert(0, turn)
                current_tokens += turn_tokens
            else:
                discarded_history.insert(0, turn)

        orphans = self._strip_orphan_tool_messages(retained_history)
        if orphans:
            current_tokens -= sum(self.count_message_tokens(m) for m in orphans)
            discarded_history.extend(orphans)

        if discarded_history:
            if tracer:
                tracer.add_step(
                    step_type="CONTEXT_COMPACTION",
                    input_data={
                        "discarded_turns": len(discarded_history),
                        "budget_tokens": self.max_tokens,
                    },
                )

            text_to_summarize = "".join(
                str(t.get("role")) + ": " + str(t.get("content")) + "\n" for t in discarded_history
            )
            summary = self.summarize(text_to_summarize, tracer=tracer)
            summary_message = {
                "role": "system",
                "content": "Summary of previous conversation:\n" + summary,
            }

            retained_history.insert(0, summary_message)
            current_tokens += self.count_message_tokens(summary_message)

            # Replace the caller's history in place so the compacted version is
            # what gets persisted and returned to the frontend.
            history.clear()
            history.extend(retained_history)

        messages.extend(retained_history)

        if memory_message is not None:
            # Placed next to the current turn rather than at the top of the
            # prompt. Buried above twenty turns of history, the facts were
            # reliably ignored; adjacent to the question being asked, they get
            # used. The user's message stays last.
            insert_at = len(messages)
            if messages and messages[-1].get("role") == "user":
                insert_at -= 1
            messages.insert(insert_at, memory_message)

        reduction_percentage = 0.0
        if original_tokens > 0 and current_tokens < original_tokens:
            reduction_percentage = round(
                (original_tokens - current_tokens) / original_tokens * 100, 2
            )

        metadata = {
            "budget_tokens": self.max_tokens,
            "original_tokens": original_tokens,
            "final_tokens": current_tokens,
            "reduction_percentage": reduction_percentage,
            "retained_turns_count": len(retained_history),
            "discarded_turns_count": len(discarded_history),
            "retained_memories": retained_memories,
        }

        return {"messages": messages, "metadata": metadata}
