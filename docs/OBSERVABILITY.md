# Observability

## Philosophy
No external logger. GlassBox observability is native. 

## Traced Entities
- **Runs**: Overarching session containers tracing `total_cost`, `total_tokens`, `latency`.
- **TraceSteps**: Hierarchical step logs tracking individual AI actions: `USER_INPUT`, `CONTEXT_SELECTION`, `LLM_CALL`, `TOOL_DECISION`, `VALIDATION`, `REPLAN`, `FINAL_RESPONSE`.

## Data Storage
Traces are explicitly recorded in SQLite, retaining `input_data`, `output_data`, and context metrics without logging private chain-of-thought representations.
