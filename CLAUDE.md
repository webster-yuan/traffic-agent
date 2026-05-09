# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> AGENTS.md is the exhaustive project manual (skill system, rules hierarchy, Qcoder agents). Read it for deep context. This file is the practical quick-reference.

## Commands

```powershell
# Backend — activate venv, then run
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend
npm run dev                # Vite dev server (port 5173)
npm run build              # typecheck + production build
npm test                   # Vitest (7 test cases)

# Tests — run from backend/
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
.venv\Scripts\python.exe -m pytest tests/ -v -k "test_name_pattern"  # single test

# LangGraph Studio (debugging only, not for business backend)
langgraph dev --host 127.0.0.1 --port 2024 --config langgraph.json

# Cleanup
python backend/cleanup.py           # remove data older than 30 days
python backend/cleanup_schedule.py  # schedule periodic cleanup

# Kill dev processes
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Stop-Process -Name node -Force -ErrorAction SilentlyContinue
```

## Architecture

**Stack**: FastAPI (Python 3.11+) + LangGraph 1.x + Ollama (qwen2.5:7b) / Vue 3 + Pinia + Vite + TypeScript / SQLite (aiosqlite + AsyncSqliteSaver)

### Supervisor-Worker Multi-Agent Graph

The core is a LangGraph `StateGraph` with 6 nodes and conditional routing. All state flows through `GraphState` (TypedDict in `backend/app/graph/state.py`):

```
START → supervisor → [rag | generate | eval | approval | identity] → supervisor (loop)
                                                                     → END
```

- **`supervisor`** (`supervisor.py`): LLM-driven routing via `RouterDecision` structured output. Two routing modes: sequential (`Command(goto=...)`) and parallel fan-out (`Send()` to eval+identity concurrently in `full` stage). Falls back to deterministic `_fallback_route()` on LLM failure.
- **`rag`** (`workers.py`): Loads 12 industry-specific example JSONs from `backend/data/examples/`, infers scenario.
- **`generate`** (`workers.py` + `generate_subgraph.py`): Invokes a nested subgraph (`prepare_prompt → call_llm → parse_result`). Subgraph state is `GenerateSubState` — isolated from parent orchestration. Supports prompt self-optimization via `eval_feedback` injection (P3.7 feedback loop).
- **`eval`** (`workers.py`): Pandera-based quality scoring: format (30%), business (40%), diversity (30%). On failure, builds `eval_feedback` for the generate worker's next retry.
- **`approval`** (`workers.py`): Human-in-the-Loop via LangGraph `interrupt()`. Graph suspends, frontend calls `POST /resume/{session_id}` with approve/reject.
- **`identity`** (`workers.py`): Identity label validation (mock in non-full stages).

**Key graph detail**: Workers return `Command(goto="supervisor")` to resume orchestration. The conditional edge `route_supervisor()` handles both string returns (sequential) and `list[Send]` (parallel fan-out).

### Service Layer

- **`services/llm_factory.py`**: Single `@lru_cache`'d `get_ollama_llm()` — all LLM instances flow through this.
- **`services/graph_runner.py`**: `build_initial_state()` + `run_generation_graph_async()` + `replay_from_checkpoint()` (Time Travel via `aget_state_history`).
- **`services/quality_validator.py`**: Pandera `DataFrameModel` with 15 declarative check rules.
- **`services/generator.py`**: LLM generation logic, quality evaluation, CSV/JSON/Parquet export.
- **`services/session_service.py`**: SQLite CRUD with 7-dimension filtering + pagination.
- **`services/tracing_config.py`**: LangSmith `build_graph_config()` — use this instead of calling LangSmith APIs from routes/nodes.
- **`services/token_counter.py`**: Token consumption tracking with sliding window stats.
- **`services/system_metrics.py`**: In-memory P50/P95/P99 latency tracking.

### Routes (`backend/app/api/`)

Routes split by domain into 6 modules under a parent `APIRouter(prefix="/api/v1/traffic")`:

- **`api/generate.py`** — `POST /generate`, `POST /generate/stream` (SSE), `DELETE /generate/{id}`, `POST /resume/{id}` (HITL)
- **`api/history.py`** — `GET /history` (7-dimension filter + pagination), `DELETE /history/{id}`, `GET /download/{id}` (csv/json/parquet)
- **`api/batch.py`** — `POST /batch` (max 10 tasks, `asyncio.Semaphore(3)` concurrency), `GET /batch/{id}`, `POST /batch/{id}/retry-failed`
- **`api/checkpoints.py`** — `GET /checkpoints/{id}`, `POST /replay`
- **`api/observability.py`** — `GET /report/{id}` (ECharts HTML), `GET /industries`, `GET /metrics`, `GET /model-info`
- **`api/deps.py`** — shared semaphore + `_run_single_task()` helper

### Frontend (`frontend/src/`)

Three panel components (`GeneratePanel.vue`, `BatchPanel.vue`, `HistoryPanel.vue`) driven by a single Pinia store (`trafficStore.ts`). SSE event stream parsed into typed callbacks: stage start/progress/complete, thoughts, token usage, approval required. The API client (`trafficApi.ts`) handles `EventSource` with `AbortController` cancellation.

### Data Flow

1. Frontend POSTs `TrafficGenerateRequest` to `/generate/stream` (SSE)
2. Route creates session in SQLite, builds initial `GraphState`, invokes graph with `astream_events()`
3. Each node streams `custom` events (stage_start, thought, generate_progress, token_usage, approval_required)
4. On `GraphInterrupt` (HITL), the route saves partial state to DB and yields `approval_required` event
5. Frontend calls `/resume/{session_id}` with approve/reject → route feeds `Command(resume=...)` back to graph
6. On completion, results written as CSV + JSON + Parquet to `backend/data/outputs/`

## Key Conventions

- **Python type annotations required** — use TypedDict for graph state, Pydantic for API models
- **Graph node signature**: `async def xxx_node(state: GraphState) -> Command[dict]`
- **No business logic in routes** — delegate to `services/`
- **No direct DB access from graph nodes** — go through `db/database.py` or `services/session_service.py`
- **Cancellation**: use `app.core.state.is_cancelled(session_id)` and `app.graph.shared.check_cancelled()`. Cancellation is cooperative — it checks a flag, doesn't kill in-flight LLM calls.
- **All LLM calls** go through `app.services.llm_factory.get_ollama_llm()` (cached singleton)
- **LangSmith tracing**: use `app.services.tracing_config.build_graph_config()` for metadata
- **Commit messages**: Chinese, single-line, bracket-prefixed tags like `[ADD]…`, `[FIX]…`, `[DOC]…` (matching pre-`ec85546` style). Confirm with user before committing.
- **After any task where you started dev servers** (uvicorn/Vite), terminate them before closing out.
- **`backend/data/`**, `.langgraph_api/`, generated CSVs, SQLite WAL/SHM, and frontend `dist/` are runtime artifacts — don't commit.

## Test Mapping

When you change a file, run the corresponding test:

| Source changed | Run |
|---|---|
| `graph/supervisor.py`, `graph/workers.py` | `test_nodes.py` + `test_graph_runner.py` |
| `services/generator.py`, `services/quality_validator.py` | `test_quality_evaluator.py` + `test_generator_industries.py` |
| `api/generate.py` | `test_routes.py`::TestRoutes + `test_batch.py` |
| `services/session_service.py` | `test_session_service.py` |
| `core/json_utils.py` | `test_json_utils.py` |
| `api/history.py`, `api/batch.py`, `api/checkpoints.py`, `api/observability.py` | `test_routes.py` + `test_observability_routes.py` + `test_batch.py` |

## Environment

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M
LLM_TIMEOUT=300
MAX_RETRY_COUNT=3
QUALITY_PASS_THRESHOLD=70
```
