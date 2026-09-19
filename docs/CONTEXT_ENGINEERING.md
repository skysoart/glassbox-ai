# Context Engineering

## Token Budgets

The agent enforces a per-request token budget set by `CONTEXT_MAX_TOKENS`
(default **8000**). Tokens are counted locally with `tiktoken` (`cl100k_base`)
before the request is sent, falling back to a characters/4 estimate if the
encoder is unavailable. Each message is charged its content, any tool-call
payload, its name, and a small per-message overhead.

## Context Lifecycle

1. **Core system instructions** are always retained, including any passages the
   RAG pass injected for this turn.
2. **Turn pruning.** History is walked backwards from the most recent turn.
   Turns that still fit are retained; the rest are discarded.
3. **Orphan removal.** A `tool` message whose preceding assistant `tool_calls`
   message was pruned is also dropped. The chat completions API rejects a tool
   result that does not follow the call it answers, so trimming in the middle
   of a tool exchange would otherwise fail the next request.
4. **Summarisation.** Discarded turns are compressed into a single summary
   message. This is a real LLM call, so it is traced as `SUMMARIZATION` and
   billed like any other. If it fails, the context still goes out with an
   explicit note that turns were dropped.
5. **Memory placement.** Retained memories are injected immediately before the
   current user turn, not at the top of the prompt. Buried above twenty turns
   of history they were reliably ignored; adjacent to the question they get
   used. Memories may claim at most half the budget.

## Visibility

`CONTEXT_SELECTION` carries the full picture for every request:

| Field | Meaning |
| --- | --- |
| `budget_tokens` | The ceiling in force for this request |
| `original_tokens` | Cost of the full context before pruning |
| `final_tokens` | Cost of what was actually sent |
| `reduction_percentage` | Measured reduction, computed from the two above |
| `retained_turns_count` / `discarded_turns_count` | Turns kept and dropped |
| `retained_memories` | The memories that made it into the prompt |

These figures are also mirrored onto the run record, so the runs list can show
them without loading every step.
