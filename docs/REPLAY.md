# Replay and Export

## Trace Export — implemented

Any run can be downloaded whole:

```
GET /api/runs/{run_id}/export
```

It returns a `glassbox.trace.v1` document containing the run record and every
trace step in order, with inputs, outputs, tool arguments, tool results, token
usage, costs and errors. The **Export Log** button on the run detail page
downloads this directly from the API, so the file is the canonical trace rather
than a re-serialisation of whatever the page happens to render.

## Deterministic Replay — not implemented

A trace captures enough to re-execute a run against recorded tool results
instead of live ones: every `TOOL_DECISION` stores the arguments and every
`TOOL_RESULT` stores what came back.

**That replay engine does not exist yet.** There is no replay endpoint and no
replay UI. This file previously described the feature as though it were built;
it is recorded here as a design note and an open item, not a capability.

Implementing it would mean: loading a trace, substituting a tool executor that
returns the recorded result for each call in order, and running the normal
agent loop against it — with the LLM call itself either replayed from the
trace or re-issued, depending on whether you are debugging the model's
decisions or the code around them.
