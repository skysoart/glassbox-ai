# Failures & Recovery

## Validator Implementation
The system implements a rigorous `Validator` layer that intercepts every agent decision.
- **Wrong Tool Selection:** If the LLM hallucinates a tool, it is caught.
- **Malformed Arguments:** Caught via schema validation.

## The REPLAN Loop
Instead of crashing, failure triggers a `REPLAN` trace. The agent is passed the error context via a system message and allowed up to 3 retries to self-correct before safely exiting.
