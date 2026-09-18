# GlassBox AI
"See exactly what your AI did."

## Overview
GlassBox AI is an observable AI agent platform built to solve the "Glass Box Problem." 
It ensures that the complete execution of an AI agent can be inspected, explained, measured, debugged, and replayed.

Unlike generic chatbot wrappers, GlassBox AI exposes its entire internal pipeline through a custom real-time telemetry frontend. It features a strict "aircraft black-box" aesthetic that presents highly dense data—showing you precisely what context was injected, what tools were called, and how much each step cost.

## Core Features
- **Strict Context Management:** Actively prunes history using a strictly bounded context manager, calculating tokens locally before hitting the API.
- **Inline RAG Pipeline:** Automatically intercepts queries, chunks your internal knowledge base (`docs/`), and dynamically injects relevant context directly into the system prompt to reduce hallucinations.
- **Trace Execution Engine:** Every step of the agent loop is saved into a local SQLite database (`glassbox.db`) via SQLAlchemy, capturing execution times, token counts, error states, and tool arguments natively.
- **Session Continuation:** Reconstructs your past chat histories from backend traces, allowing you to instantly revisit and continue old conversations via the "Sessions" sidebar.
- **Flight Recorder UI:** A dense, 1px-hairline, custom React frontend designed for utility and observability rather than SaaS aesthetics.

## Tech Stack
- **Backend:** Python, FastAPI, SQLAlchemy, SQLite, OpenAI API (via Gemini compatibility)
- **Frontend:** React, TypeScript, Tailwind CSS, Vite
- **Model:** Gemini-3.5-Flash-Lite (via OpenAI provider interface for native tool-calling support)

## Getting Started

### 1. Backend Setup
Navigate to the `backend` directory, set up your virtual environment, and run the server.

```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

**Environment Variables:**
Create a `.env` file in the `backend/` folder based on `.env.example`:
```env
LLM_API_KEY=your_gemini_api_key_here
LLM_MODEL=gemini-3.5-flash-lite
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
DATABASE_URL=sqlite:///./glassbox.db
LLM_PROVIDER=openai
```

Start the backend:
```bash
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup
Navigate to the `frontend` directory and start the Vite dev server.

```bash
cd frontend
npm install
npm run dev
```

Navigate to `http://localhost:5173` in your browser.

## Documentation
See the `docs/` folder for detailed guides on:
- **ARCHITECTURE.md**: System component breakdown and request lifecycles.
- **OBSERVABILITY.md**: How tracing and token management works.
- **CONTEXT_ENGINEERING.md**: The philosophy behind the strictly bounded context.
- **FAILURES.md**: Error boundaries and recovery patterns.

## Collaborators

- [Garvit Dalakoti](https://github.com/skysoart)
- [Dhruv Tilara](https://github.com/Dhruvtilara)
- [Khushal Jangid](https://github.com/khushal123supreme)
