---
name: traffic-agent-iteration-validation
description: Runs the Traffic Agent iteration validation workflow. Use after each feature, task, or bugfix in this project, especially when frontend, FastAPI routes, LangGraph execution, task persistence, LangSmith tracing, or generated outputs changed.
---

# Traffic Agent Iteration Validation

## When To Use

Use this skill after completing any iteration task in Traffic Agent:

- New feature or UI change
- Backend API or database change
- LangGraph workflow or LangSmith tracing change
- Task lifecycle/status/history change
- Any fix that affects local generation behavior

## Workflow

1. Run focused automated tests.
   - Backend from `backend/`: `.venv\Scripts\python.exe -m pytest -q ...`
   - Frontend from `frontend/`: `npm test`
   - If frontend files changed: `npm run build`

2. Start the local services needed for the scenario.
   - Prefer the normal ports: backend `8000`, frontend `5173`.
   - If a stale Windows listener blocks `8000`, start backend on `8001` and frontend on `5174` with:
     - backend: `uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`
     - frontend: `$env:VITE_API_BASE='http://127.0.0.1:8001/api/v1/traffic'; npm run dev -- --host 127.0.0.1 --port 5174`

3. Run a real browser scenario with Chrome DevTools MCP.
   - Open the frontend page.
   - Use `stage=quick` and `count=2`.
   - Submit generation.
   - Verify the page shows `Session ID`, task progress, final download link, and a new history row.
   - Inspect Network for `generate/stream` and `history` returning `200`.
   - Inspect Console for errors.

4. Verify persisted task data when task persistence changed.
   - Call `/api/v1/traffic/history?page=1&page_size=1`.
   - Confirm `status`, `requested_count`, `record_count`, `trace_thread_id`, `started_at`, and `completed_at` are correct.

5. Clean up dev servers started for validation.
   - Stop only the services started during this validation run.
   - Do not kill user-owned processes unless explicitly requested.

## Final Summary Template

End each iteration with:

- What changed
- Automated tests run and results
- Browser scenario result
- Any residual risk or known issue
- Whether the experience should become:
  - Cursor Rule for project habits
  - Skill for repeated workflows
  - MCP configuration for external system control

## Project Constraints

- Keep generation tests small because local Ollama is resource constrained.
- Do not commit runtime artifacts from `backend/data/`, generated CSV files, SQLite WAL/SHM files, frontend `dist/`, or LangGraph local runtime folders.
- Keep LangSmith integration decoupled through `build_graph_config()` metadata rather than direct LangSmith API calls inside route handlers or graph nodes.
