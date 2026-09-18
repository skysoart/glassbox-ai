# Demo Script

1. **Start the System**: Launch the FastAPI backend and Vite frontend.
2. **Perform Normal Chat**: Ask "What is 20 + 20?" to trigger the calculator tool.
3. **View Dashboard**: Open the Dashboard to see real cost and token tracking for your chat.
4. **Context Inspector**: Click the specific trace, expand `CONTEXT_SELECTION`, and observe how token budgets were enforced.
5. **Failure Lab**: Trigger the "Wrong Tool" scenario. Observe how the validator catches the hallucinated tool and triggers a `REPLAN` loop instead of crashing.
6. **Stress Test**: Run the 20+ turn stress test to demonstrate memory retention and context pruning limits.
