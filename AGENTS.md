# AGENTS.md — Traffic Agent

> Qoder CLI `/init` 等效产物。项目内 `.qcoder/skills/` 配置了 Superpowers（宏观工程纪律）+ ECC（实现细节与专项检查）双技能体系。

> **⚠️ 开发任务第一入口**：在开始任何开发任务前，AI 工具和开发者必须优先读取 [`docs/SKILL_INVOCATION_GUIDE.md`](docs/SKILL_INVOCATION_GUIDE.md)，该文档定义了完整的 Skill 调用逻辑、场景化路径和优先级规则。本文档为项目说明书，SKILL_INVOCATION_GUIDE.md 为执行标准书，两者互补。

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

> **详细调用逻辑、场景化路径、优先级规则 → 请参阅 [`docs/SKILL_INVOCATION_GUIDE.md`](docs/SKILL_INVOCATION_GUIDE.md)**（执行标准书，第一入口）

### 3.0 Qcoder Agents（项目级子代理）

> **配置目录**：`.qcoder/agents/` — qcoder 启动时自动发现并加载

本项目从 ECC agents 库中精选了 12 个与技术栈匹配的子代理：

| Agent | 用途 | 触发时机 |
|-------|------|---------|
| `python-reviewer` | Python/FastAPI/LangGraph 代码审查 | 任何 Python 代码变更后 |
| `code-reviewer` | 通用全栈代码审查 | 代码写入后 |
| `tdd-guide` | pytest TDD 红绿重构流程 | 新功能、Bug 修复 |
| `planner` | 复杂功能实施计划 | 需求明确后的规划阶段 |
| `architect` | 系统架构设计 | 架构决策、技术选型 |
| `security-reviewer` | 安全漏洞扫描 | 提交前 |
| `e2e-runner` | Chrome 全链路浏览器测试 | 关键用户流程验证 |
| `build-error-resolver` | 构建错误诊断修复 | 构建失败时 |
| `doc-updater` | 文档同步更新 | 功能变更后 |
| `refactor-cleaner` | 死代码清理 | 代码维护 |
| `code-explorer` | 代码库探索分析 | 理解现有功能前 |
| `code-simplifier` | 代码简化降复杂度 | 重构优化 |

> **Agent vs Skill 的关系**：Skill 定义流程和规范（"怎么做"），Agent 是执行单元（"谁来做"）。Skill 调用链中的 `subagent-driven-development` 会自动分派合适的 Agent 执行具体任务。

### 3.0a Qcoder Rules（项目级编码规范）

> **配置目录**：`.qcoder/rules/` — 分层规则体系，common 定义通用标准，语言层覆盖特定技术栈

从 ECC rules 库中精选了 3 套规则（22 个文件），按优先级叠加：

```
.qcoder/rules/
├── common/    (10 文件) — 语言无关的通用标准
│   ├── coding-style.md        # KISS/DRY/YAGNI、不可变性、文件组织
│   ├── testing.md             # 80% 覆盖率、TDD 流程、AAA 模式
│   ├── security.md            # 安全检查清单、密钥管理
│   ├── git-workflow.md        # commit 格式、PR 工作流
│   ├── development-workflow.md # Research→Plan→TDD→Review→Commit 全流程
│   ├── code-review.md         # 审查清单、严重级别、审批标准
│   ├── agents.md              # Agent 编排、并行执行、多视角分析
│   ├── patterns.md            # Repository 模式、API 响应格式
│   ├── performance.md         # 模型选择策略、上下文管理
│   └── hooks.md               # Hook 系统架构
├── python/    (5 文件) — Python/FastAPI 专用
│   ├── coding-style.md        # PEP 8、类型注解、black/isort/ruff
│   ├── testing.md             # pytest、mark 分类、覆盖率命令
│   ├── security.md            # bandit 扫描、环境变量密钥管理
│   ├── patterns.md            # Protocol、dataclass、context manager
│   └── hooks.md               # PostToolUse: ruff format + mypy 检查
└── web/       (7 文件) — Vue/TypeScript 前端专用
    ├── coding-style.md        # 文件组织、CSS 变量、动画属性、语义化 HTML
    ├── testing.md             # 视觉回归、可访问性、性能、跨浏览器
    ├── design-quality.md      # 前端设计质量检查
    ├── patterns.md            # Web 设计模式
    ├── security.md            # 前端安全
    ├── performance.md         # 前端性能
    └── hooks.md               # Web 专属 Hook
```

> **Rules vs Skills 的关系**：Rules 定义标准和约束（"要做什么"），Skills 提供深度参考（"怎么做"）。如 `rules/python/testing.md` 要求 80% 覆盖率，`skills/python-testing` 教怎么写 pytest 测试。

### 3.0b Qcoder Commands（自定义斜杠命令）

> **配置目录**：`.cursor/commands/` — Markdown 格式的结构化工作流，可通过 `/command` 调用

从 ECC commands 库中精选了 8 个与项目技术栈匹配的命令：

| 命令 | 用途 | 触发场景 |
|------|------|---------|
| `/python-review` | Python 专项审查（PEP 8、类型、安全） | Python 代码变更后 |
| `/code-review` | 通用代码审查（本地 diff + GitHub PR） | 提交前 |
| `/feature-dev` | 引导式功能开发（7 阶段） | 新功能启动 |
| `/plan` | 需求→风险→实施计划（等待确认） | 复杂任务规划 |
| `/test-coverage` | 覆盖率分析 + 补测（目标 80%+） | 提交前质量检查 |
| `/refactor-clean` | 死代码清理（安全分级删除） | 代码维护 |
| `/quality-gate` | 格式化→lint→类型检查一键流水线 | 合并前最终检查 |
| `/evolve` | 实践→结构演化（Skill/Agent 孵化） | 重复模式自动化 |

> **Commands vs Agents 的关系**：Commands 是用户主动调用的工作流入口，Agent 是被动分派的执行单元。Command 内部可以自动触发 Agent。

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

> **完整场景路径和每一步调用的 Skill → 参阅 SKILL_INVOCATION_GUIDE.md 第二章**

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
├── .qcoder/rules/             # 项目级编码规范（common + python + web）
│   ├── common/                # 语言无关通用规则（10 文件）
│   ├── python/                # Python 专用规则（5 文件）
│   └── web/                   # 前端专用规则（7 文件）
├── .qcoder/agents/            # 项目级子代理（12 个）
├── .cursor/commands/          # 自定义斜杠命令（8 个）
├── .cursor/hooks/             # 事件驱动自动化（预留，待配置）
├── .cursor/mcp-configs/       # MCP 服务器配置（预留，待配置）
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

---

## 九、外部配置源（ECC 引用）

> **原则**：本项目 `.qcoder/` 和 `.cursor/` 中的配置从 [everything-claude-code](https://github.com/affaan-m/everything-claude-code) 仓库精选而来。后续开发中遇到需要新增的配置类型，**优先去该仓库查找**，找到合适的配置后复制回本项目，而非从零编写。

### 9.1 已集成的 ECC 配置

| 配置类型 | 目标目录 | 数量 | 状态 |
|---------|---------|------|------|
| Skills | `.qcoder/skills/` | 192 目录 | ✅ 已完成 |
| Agents | `.qcoder/agents/` | 12 文件 | ✅ 已完成 |
| Rules | `.qcoder/rules/` | 22 文件（3 套） | ✅ 已完成 |
| Commands | `.cursor/commands/` | 8 文件 | ✅ 已完成 |

### 9.2 ECC 中可用的其他配置类型（按需引入）

| 配置类型 | ECC 源路径 | 目标路径 | 何时引入 |
|---------|-----------|---------|---------|
| **Hooks** | `hooks/hooks.json` + `scripts/hooks/` | `.cursor/hooks/` + `.cursor/hooks.json` | 需要自动化质量检查时（如编辑后自动 ruff format） |
| **MCP Servers** | `mcp-configs/mcp-servers.json` | `.cursor/mcp-configs/` | 需要 Jira/GitHub/Playwright/Context7 等外部工具集成时 |
| **Contexts** | `contexts/dev.md`, `review.md`, `research.md` | `.cursor/contexts/` | 需要定义不同工作模式的 AI 行为时 |
| **CI Workflows** | `.github/workflows/` | `.github/workflows/` | 需要 GitHub Actions CI/CD 时 |

### 9.3 引入流程

```
1. 确认需求 → 需要哪种配置？
2. 查阅 ECC → [everything-claude-code](https://github.com/affaan-m/everything-claude-code) 仓库中是否有对应配置？
3. 筛选适配 → 根据项目技术栈精选相关文件
4. 复制到项目 → 放入对应 .qcoder/ 或 .cursor/ 子目录
5. 更新文档 → 在本文档 3.0x 节和 SKILL_INVOCATION_GUIDE.md 中补充说明
```

> **ECC 仓库完整目录**：参考 [`SKILL_INVOCATION_GUIDE.md`](docs/SKILL_INVOCATION_GUIDE.md) 第九章（ECC 仓库结构与配置速查）
