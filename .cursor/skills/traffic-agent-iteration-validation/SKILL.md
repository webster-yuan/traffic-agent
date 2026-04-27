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

3. **Start Chrome with remote debugging** (required before DevTools MCP; use a separate profile from your daily browser).
   - **Windows (PowerShell)** — run as a single block, then keep this Chrome window open for step 4:
     ```powershell
     $chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
     if (-not (Test-Path $chrome)) { throw "Install Google Chrome or adjust path." }
     $profile = Join-Path $env:TEMP "traffic-agent-chrome-mcp-profile"
     New-Item -ItemType Directory -Force -Path $profile | Out-Null
     if (-not (Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue)) {
       Start-Process -FilePath $chrome -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=$profile"
     }
     ```
   - **Verify the debugger** is up: `curl.exe http://127.0.0.1:9222/json/version` (or open in browser) should return JSON. If port `9222` is already in use, assume a debuggable Chrome is running and skip `Start-Process`.
   - More context: repository `README.md` section **Chrome DevTools MCP**.

4. Run a real browser scenario with Chrome DevTools MCP.
   - Open the frontend: `http://127.0.0.1:5173/` (or `5174` if you used alternate ports in step 2).
   - Use `stage=quick` and `count=2`.
   - Submit generation（「开始生成」）.
   - Verify the page shows `Session ID`, task progress, final download area（**CSV | JSON | Parquet** 等约定链接）, and a new history row.
   - 等待全链路完成时，优先等待当前 `session_id` 对应的下载路径片段（如 `/api/v1/traffic/download/{session_id}`）出现在结果区，避免用「重试」等易与说明文案（如「最多重试」）撞车的关键词驱动 `wait_for`。
   - Inspect Network for `generate/stream` and `history` returning `200`.
   - Inspect Console for errors (ignore benign Vite HMR / dev-only messages if appropriate).

5. Verify persisted task data when task persistence changed.
   - Call `/api/v1/traffic/history?page=1&page_size=1`.
   - Confirm `status`, `requested_count`, `record_count`, `trace_thread_id`, `started_at`, and `completed_at` are correct.

6. Update `ROADMAP.md` before committing.
   - Mark the completed to-do item as done or update its status.
   - Refresh the current project state if the iteration changed capabilities, risks, or the next recommended task.
   - Keep this documentation update in the same concern area or in a separate docs commit when appropriate.

7. **Always** clean up dev servers you started for this run (mandatory before finishing the task).
   - Stop the **backend** (uvicorn) and **frontend** (`npm run dev`) you started for Traffic Agent validation.
   - If you started a **Chrome** instance only for MCP (e.g. `--remote-debugging-port=9222` with a temp `--user-data-dir`), close that process as well (or stop the listener on `9222` if you own it and no other work depends on it).
   - Do not kill unrelated processes or servers the user already had running on other ports.
   - **Windows (PowerShell)**: find listener PIDs then stop, e.g. for ports used in this session:
     ```powershell
     8000,5173 | ForEach-Object {
       Get-NetTCPConnection -LocalPort $_ -ErrorAction SilentlyContinue |
         ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
     }
     ```
     Adjust port list to match what you started (e.g. `8001,5174`). If you started Chrome in step 3 and need to free `9222`, add `9222` to the list **only** when you are sure it is the MCP-dedicated instance. If you recorded PIDs when spawning `Start-Process`, `Stop-Process -Id <pid> -Force` is preferred.

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
