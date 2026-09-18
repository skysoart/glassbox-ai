import tiktoken
from typing import List, Dict, Any
from app.agent.llm_provider import get_provider

class ContextManager:
    def __init__(self, max_tokens: int = 500000):
        self.max_tokens = max_tokens
        self.provider = get_provider()
        try:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except:
            self.encoder = None

    def count_tokens(self, text: str) -> int:
        if self.encoder:
            return len(self.encoder.encode(text))
        return len(text) // 4  # rough fallback

    def summarize(self, text_to_summarize: str) -> str:
        prompt = f"Please summarize the following conversation history concisely, retaining all important facts and context:\n\n{text_to_summarize}"
        # We can just call provider.generate directly. No tools needed.
        result = self.provider.generate([{"role": "user", "content": prompt}])
        return result.get("content", "Summary failed.")

    def build_context(self, system_prompt: str, history: List[Dict[str, Any]], memories: List[str] = None, tracer=None) -> Dict[str, Any]:
        """
        Builds the context within the budget.
        Returns the finalized messages array, and metadata for the trace (tokens reduced, what was kept)
        """
        messages = [{"role": "system", "content": system_prompt}]
        current_tokens = self.count_tokens(system_prompt)
        
        retained_memories = []
        if memories:
            memory_text = "Important Facts:\n" + "\n".join(memories)
            mem_tokens = self.count_tokens(memory_text)
            if current_tokens + mem_tokens < self.max_tokens / 2:
                messages.append({"role": "system", "content": memory_text})
                current_tokens += mem_tokens
                retained_memories = memories
                
        # We need to see if the whole history fits.
        # If not, we will summarize the older part.
        retained_history = []
        discarded_history = []
        
        # We iterate backwards to keep recent turns.
        for turn in reversed(history):
            turn_content = str(turn.get("content", ""))
            if turn.get("tool_calls"):
                turn_content += str(turn["tool_calls"])
            turn_tokens = self.count_tokens(turn_content) + 10
            
            if current_tokens + turn_tokens <= self.max_tokens:
                retained_history.insert(0, turn)
                current_tokens += turn_tokens
            else:
                discarded_history.insert(0, turn)
                
        if discarded_history:
            # We have discarded history. Let's summarize it.
            if tracer:
                tracer.add_step(step_type="CONTEXT_COMPACTION", input_data={"discarded_turns": len(discarded_history)})
            
            text_to_summarize = ""
            for t in discarded_history:
                text_to_summarize += f"{t.get('role')}: {t.get('content')}\n"
            
            summary = self.summarize(text_to_summarize)
            summary_message = {"role": "system", "content": f"Summary of previous conversation:\n{summary}"}
            
            # Prepend summary to retained history
            retained_history.insert(0, summary_message)
            current_tokens += self.count_tokens(summary_message["content"])
            
            # Modify the original history in-place so the frontend gets the compressed version!
            history.clear()
            history.extend(retained_history)
                
        messages.extend(retained_history)
        
        original_tokens = sum([self.count_tokens(str(m)) for m in history])
        # If we summarized, original_tokens might now reflect the already summarized history length, 
        # but that's okay. We reduced it.
        
        metadata = {
            "original_tokens": original_tokens,
            "final_tokens": current_tokens,
            "reduction_percentage": 0,
            "retained_turns_count": len(retained_history),
            "discarded_turns_count": len(discarded_history),
            "retained_memories": retained_memories
        }
        
        return {
            "messages": messages,
            "metadata": metadata
        }
