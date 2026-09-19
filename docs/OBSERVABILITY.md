# Observability

## Philosophy

No external logger. GlassBox observability is native: the trace is written by
the agent loop itself, into the same SQLite database the UI reads.

## Traced Entities

- **Runs**: session containers carrying `total_cost`, `total_tokens`,
  `total_latency_ms`, the per-run counters, and the context figures.
- **TraceSteps**: individual agent actions, linked to their parent step where
  one applies.

## Step Types

| Step | Recorded when |
| --- | --- |
| `USER_INPUT` | A request enters the agent |
| `RAG_RETRIEVAL` | The inline docs search runs; records matched sources |
| `CONTEXT_COMPACTION` | History had to be trimmed to fit the budget |
| `SUMMARIZATION` | Dropped turns were summarised (a real, billed LLM call) |
| `CONTEXT_SELECTION` | The final context was assembled |
| `LLM_CALL` | A model call completed |
| `TOOL_DECISION` | The model requested a tool |
| `VALIDATION` | The validator checked a tool call |
| `TOOL_RESULT` | A tool executed |
| `REPLAN` | A validation or tool failure requires another attempt |
| `RETRY` | The loop went back for another attempt |
| `FINAL_RESPONSE` | The model answered without requesting tools |
| `FAILURE` | The run ended without an answer |

## Run Counters

Counters are driven by a single table in the collector, keyed on the step types
the agent actually emits:

| Counter | Incremented by |
| --- | --- |
| `llm_call_count` | `LLM_CALL`, `SUMMARIZATION` |
| `tool_call_count` | `TOOL_DECISION` |
| `validation_count` | `VALIDATION` |
| `retry_count` | `RETRY` |
| `failure_count` | Any step recorded with status `FAILED` |

## Run Status

- `SUCCESS` — completed with no failures or retries.
- `RECOVERED` — hit a validation or tool failure and still answered.
- `FAILED` — ended without an answer.

## Cost Accounting

Prices live in `backend/pricing.json` (USD per 1M tokens), looked up by exact
match and then by longest prefix, so a dated model id resolves to its family.
`LLM_PRICE_INPUT` / `LLM_PRICE_OUTPUT` override it for an unlisted model.

When a model has no known price, the step is stored with `cost_known = false`
rather than a cost of zero, and the run inherits the flag. The UI then shows
`n/a` and marks affected totals as a lower bound, instead of presenting an
unpriced run as free.

## Data Storage

Traces are recorded in SQLite, retaining `input_data`, `output_data`, error
payloads and context metrics. Any run can be downloaded whole from
`GET /api/runs/{run_id}/export` as a `glassbox.trace.v1` JSON document.
