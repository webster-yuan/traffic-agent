# AGENTS.md — Traffic Agent

> Qoder CLI `/init` 等效产物。项目内 `.qcoder/skills/` 配置了 Superpowers（宏观工程纪律）+ ECC（实现细节与专项检查）双技能体系。

---

## 一、项目概述

**Traffic Agent** — 基于 LangGraph 自研 Supervisor-Worker 多智能体编排引擎，实现 AI 驱动的高真实度网络流量数据自动生成与质量评估系统。

## 二、技术栈

| 层 | 技术 |
|----|------|
| **后端框架** | FastAPI + uvicorn (port 8000) |
| **AI 编排** | LangGraph 1.x (StateGraph + Send() + Subgraph) |
| **LLM** | Ollama 本地部署 (qwen2.5:7b) |
| **数据库** | SQLite (AsyncSqliteSaver checkpoint + aiosqlite) |
| **质量校验** | Pandera 声明式 Schema（15 条规则） |
| **可观测** | LangSmith (@traceable) + SSE 思考链 |
| **前端** | Vue 3 + Pinia + Vite + TypeScript |
| **测试** | pytest (55 cases) |
| **环境** | Windows 10 + PowerShell |

## 三、Skill 体系与分工

本项目配置了两套互补的 Skill 体系，按职责明确分工，避免冲突：

### 3.1 Superpowers — 宏观流程与工程纪律

**职责**：控制"怎么做"的流程，确保开发过程规范可控。

| 技能 | 触发场景 |
|------|---------|
| `brainstorming` | 进入 Plan Mode 前、需求不明确时 |
| `writing-plans` | 复杂任务开始前，先写计划 |
| `subagent-driven-development` | 有计划且任务独立时，逐任务分派子 Agent 执行 |
| `executing-plans` | 任务可完全并行时，开独立 Session |
| `test-driven-development` | 新增功能或修 bug 时，先写失败测试 |
| `systematic-debugging` | 任何 bug / 测试失败 / 异常，**修复前必须先找根因** |
| `dispatching-parallel-agents` | 2+ 独立问题域可同时处理时 |
| `requesting-code-review` | 每个任务完成后、合并前 |
| `receiving-code-review` | 收到审查反馈时 |
| `finishing-a-development-branch` | 所有任务完成后，合并前收尾 |
| `verification-before-completion` | **任何完成声明前，必须运行验证命令并确认输出** |
| `using-git-worktrees` | 需要隔离工作区时（可选） |
| `writing-skills` | 创建/编辑项目 Skill 时 |
| `using-superpowers` | 启动会话时，确认技能发现与调用规则 |

### 3.2 ECC — 实现细节与专项检查

**职责**：控制"写成什么样"的质量，提供领域最佳实践。

| 技能 | 触发场景 |
|------|---------|
| `python-patterns` | 编写/评审 Python 代码 |
| `python-testing` | 编写 pytest 测试 |
| `backend-patterns` | 设计 API、数据库优化、中间件 |
| `frontend-patterns` | Vue/TypeScript 前端开发 |
| `frontend-design` | UI 美化、交互设计 |
| `api-design` | 新增/修改 REST API 端点 |
| `security-review` | 认证、用户输入、敏感操作 |
| `database-migrations` | 修改数据库 schema |
| `prompt-optimizer` | 优化 LLM Prompt |
| `e2e-testing` | 全链路浏览器验证 |
| `docker-patterns` | Docker 化（远期） |
| `postgres-patterns` | PostgreSQL 迁移（远期） |
| `agentic-engineering` | Agent 架构设计 |
| `ai-first-engineering` | AI 驱动开发模式 |
| `verification-loop` | 修改后自检是否达标 |
| `code-tour` | 为新成员介绍代码库 |

### 3.3 协作顺序

```
新功能 / 复杂需求：
  brainstorming → writing-plans → subagent-driven-development
    → 每个子任务内：test-driven-development + python-patterns/backend-patterns
    → requesting-code-review → verification-before-completion
    → finishing-a-development-branch

简单 bug / typo / 小改动：
  systematic-debugging（定位根因）→ python-patterns → verification-before-completion

纯前端（UI/样式）：
  frontend-design + frontend-patterns → e2e-testing → requesting-code-review
```

**核心原则**：
- Superpowers 负责流程走对，ECC 负责代码写好
- 新功能必须过 Superpowers 规划链路，再借 ECC 落地细节
- 简单 bug 可跳过规划，直接用 ECC，但仍需 `systematic-debugging` 找根因
- `verification-before-completion` 是**最终出口条件**——没有运行验证，不得声称完成

### 3.4 项目专用 Skill

| 技能 | 说明 |
|------|------|
| `traffic-agent-dev-workflow` | 本项目标准 8 步开发流程（阅读→实现→自测→全链路→清理→文档→汇报→提交） |
| `traffic-agent-iteration-validation` | 迭代生成质量验证 |
| `karpathy-guidelines` | 编码原则：思考先行、简洁优先、外科手术式变更、目标驱动 |
| `langchain-requirement-skill` | LangChain/LangGraph 开发规范 |
| `git-workflow` | Git 提交流程规范 |

---

## 四、项目结构

```
traffic-agent/
├── AGENTS.md                  # ← 本文件
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口 + lifespan
│   │   ├── api/routes.py      # REST + SSE 端点
│   │   ├── core/config.py     # Settings (Ollama URL, model, paths)
│   │   ├── core/state.py      # 全局状态（取消标记）
│   │   ├── models/schemas.py  # Pydantic models (TrafficRecord)
│   │   ├── graph/state.py     # GraphState TypedDict
│   │   ├── graph/nodes.py     # supervisor + 4 workers
│   │   ├── graph/workflow.py  # build_graph() → StateGraph
│   │   ├── services/          # 业务逻辑层
│   │   │   ├── langchain_service.py  # LLM + with_structured_output
│   │   │   ├── generator.py          # 生成 + 质量评分 + 导出
│   │   │   ├── graph_runner.py       # astream_events + SSE
│   │   │   ├── quality_validator.py  # Pandera schemas
│   │   │   └── report_service.py     # HTML + ECharts 报表
│   │   └── db/database.py     # SQLite CRUD
│   ├── data/examples/*.json   # 12 行业 RAG 示例
│   └── tests/                 # pytest
├── frontend/src/              # Vue 3 + Pinia + Vite
├── docs/
│   ├── ROADMAP.md             # 路线图（权威文档）
│   ├── 开发设计文档_v2.0.md    # 后端架构（面试用）
│   └── Agent核心技术落地.md    # Agent 技术深度
├── .qcoder/skills/            # 技能库（Superpowers + ECC）
└── desc.md / resume.md        # 简历
```

## 五、开发约定

### 5.1 Git

- **Commit message**: 英文，`<type>: <description>`（feat/fix/docs/refactor/test）
- **只在用户明确要求时提交**
- 禁止 `--no-verify`、`--force` 推送到 main

### 5.2 测试

```powershell
cd backend
python -m pytest tests/ -v
```

改动映射（改什么跑什么）：
- `nodes.py` / `workflow.py` → `test_nodes.py` + `test_graph_runner.py`
- `generator.py` / `quality_validator.py` → `test_quality_evaluator.py` + `test_generator_industries.py`
- 任何后端改动 → `test_routes.py`（全栈集成）

### 5.3 代码风格

- Python：类型注解必须（TypedDict / Pydantic）
- Vue：Composition API + `<script setup lang="ts">`
- 不创建无意义的 `.md` / 临时文件

### 5.4 后端架构约束

- **不要**在 `nodes.py` 中直接操作数据库 → 通过 `db/database.py`
- **不要**在 `routes.py` 中写业务逻辑 → 通过 `services/`
- Graph 节点签名：`async def xxx_node(state: GraphState) -> GraphState`
- Supervisor conditional edge 返回 `str | list[Send]`

---

## 六、常用命令

```powershell
# 后端
cd backend; .\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend; npm run dev

# 测试
cd backend; python -m pytest tests/ -v --tb=short

# 进程清理
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Stop-Process -Name node -Force -ErrorAction SilentlyContinue
```

---

## 七、当前状态

- **已完成**：P1 核心生成 → P2 Supervisor-Worker 架构 → P3 SSE 思考链 + LangSmith 追踪
- **下一任务**：参考 `docs/ROADMAP.md` 优先级总览
- **设计文档**：`docs/开发设计文档_v2.0.md`（面试用）

---

## 八、Skill 管理规则

1. **新增 Skill**：新技能放入 `.qcoder/skills/<name>/SKILL.md`，并在本文件 3.1 或 3.2 节补充记录
2. **跨 Skill 流程**：涉及多 Skill 协作时，必须在本文件 3.3 节写明顺序与出口条件
3. **优先级**：AGENTS.md 显式指令 > Superpowers 流程 > ECC 实现细节 > 系统默认行为
