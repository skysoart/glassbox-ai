# Context Engineering

## Token Budgets
The agent strictly enforces a 4000-token limit for LLM requests to prevent degradation.

## Context Lifecycle
1. **Core System Instructions:** Always retained.
2. **Important Memories:** Explicitly fetched and statically injected if space allows.
3. **Turn Pruning:** The chat history is parsed sequentially backward. If an older turn forces the agent over the threshold, it is dropped.
4. **Visibility:** The UI explicitly details `reduction_percentage`, `retained_turns`, and `discarded_turns`.
