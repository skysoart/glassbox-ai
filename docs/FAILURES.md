# Failures & Recovery

## Validator Implementation

Every tool call is checked before it runs:

- **Wrong tool selection** — a name that is not in the accepted tool list is
  rejected, and the error names the tools that *are* available.
- **Missing required arguments** — checked against the tool's JSON schema.
- **Unexpected arguments** — an argument the schema does not declare is
  rejected rather than silently dropped.
- **Wrong argument types** — checked against the schema's declared type.
  Booleans are not accepted where a number is expected.
- **Malformed JSON** — arguments that do not parse are reported to the model as
  a validation failure instead of being swallowed into an empty dict.

Tool *results* are checked too. A result is treated as a failure when it starts
with a known error prefix. The check is anchored at the start of the string, so
a genuine search result that merely contains the word "failed" is not
misread as a tool error.

## The REPLAN Loop

A failure records `REPLAN` and returns the error to the model as the tool
result for that call, so the model sees exactly which call failed and why.
The loop then records `RETRY` and reassembles the context.

**Every tool call receives a response, including the ones that fail.** The chat
completions API rejects an assistant turn whose announced tool calls are not
all answered, so the loop never abandons a call part-way through a batch.

## Bounds

- `AGENT_MAX_RETRIES` (default 3) — replans allowed after a failure.
- `AGENT_MAX_STEPS` (default 8) — total LLM calls per request. This is the
  limit that stops a model which keeps making *valid* tool calls from looping
  forever; the retry counter alone would never fire.

When either limit is reached the run records a `FAILURE` step naming which one,
and returns a message rather than raising.

## Transient Provider Errors

Rate limits (429) and transient upstream failures (500/502/503/504, overloaded)
are retried up to three times with exponential backoff, for both providers.
Anything else is returned immediately and recorded as a `FAILURE` step.

## Provider Quirks

Gemini 3.x attaches a `thought_signature` to each tool call and rejects the
follow-up request with a 400 unless it is echoed back unchanged. The provider
captures this `extra_content` and the agent replays it verbatim on the
assistant turn.
