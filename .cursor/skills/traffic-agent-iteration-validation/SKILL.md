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
   - **Chrome 调试端口**: MCP 需连接已启用远程调试的 Chrome。可用临时用户目录启动，例如（Windows）：`& 'C:\Program Files\Google\Chrome\Application\chrome.exe' --remote-debugging-port=9222 --user-data-dir=%TEMP%\traffic-agent-chrome-mcp-profile`，并确认 `http://127.0.0.1:9222/json/version` 可访问。详见仓库 `README.md`「Chrome DevTools MCP」。
   - Open the frontend page.
   - Use `stage=quick` and `count=2`.
   - Submit generation.
   - Verify the page shows `Session ID`, task progress, final download area（含 **CSV / JSON** 等约定链接）, and a new history row.
   - 等待全链路完成时，优先等待当前 `session_id` 对应的下载路径片段（如 `/api/v1/traffic/download/{session_id}`）出现在结果区，避免用「重试」等易与说明文案（如「最多重试」）撞车的关键词驱动 `wait_for`。
   - Inspect Network for `generate/stream` and `history` returning `200`.
   - Inspect Console for errors.

4. Verify persisted task data when task persistence changed.
   - Call `/api/v1/traffic/history?page=1&page_size=1`.
   - Confirm `status`, `requested_count`, `record_count`, `trace_thread_id`, `started_at`, and `completed_at` are correct.

5. Update `ROADMAP.md` before committing.
   - Mark the completed to-do item as done or update its status.
   - Refresh the current project state if the iteration changed capabilities, risks, or the next recommended task.
   - Keep this documentation update in the same concern area or in a separate docs commit when appropriate.

6. **Always** clean up dev servers you started for this run (mandatory before finishing the task).
   - Stop the **backend** (uvicorn) and **frontend** (`npm run dev`) you started for Traffic Agent validation.
   - If you started a **Chrome** instance only for MCP (e.g. `--remote-debugging-port=9222` with a temp `--user-data-dir`), close that process as well.
   - Do not kill unrelated processes or servers the user already had running on other ports.
   - **Windows (PowerShell)**: find listener PIDs then stop, e.g. for ports used in this session:
     ```powershell
     8000,5173 | ForEach-Object {
       Get-NetTCPConnection -LocalPort $_ -ErrorAction SilentlyContinue |
         ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
     }
     ```
     Adjust port list to match what you started (e.g. `8001,5174`). If you recorded PIDs when spawning `Start-Process`, `Stop-Process -Id <pid> -Force` is preferred.

## Final Summary Template

End each iteration with:

- What changed
- Automated tests run and results
- Browser scenario result
- Whether `ROADMAP.md` was updated before commit
- Whether local **backend/frontend** (and MCP Chrome, if started) were **stopped** after validation
- Any residual risk or known issue
- Whether the experience should become:
  - Cursor Rule for project habits
  - Skill for repeated workflows
  - MCP configuration for external system control

## Project Constraints

- Keep generation tests small because local Ollama is resource constrained.
- Do not commit runtime artifacts from `backend/data/`, generated CSV files, SQLite WAL/SHM files, frontend `dist/`, or LangGraph local runtime folders.
- Keep LangSmith integration decoupled through `build_graph_config()` metadata rather than direct LangSmith API calls inside route handlers or graph nodes.
