# AGENTS.md — Traffic Agent

> 本文件是 Qoder CLI `/init` 等效产物，定义了 AI 助手在当前项目中的开发规范与工作流。
> 项目内 `.qcoder/skills/superpowers/` 提供了 14 个开发方法论技能，后续所有开发必须遵循其流程。

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
| **质量校验** | Pandera (声明式 Schema，15 条规则) |
| **可观测** | LangSmith (@traceable) + SSE 思考链 |
| **前端** | Vue 3 + Pinia + Vite + TypeScript |
| **测试** | pytest (55 cases) |
| **环境** | Windows 10 + PowerShell |

## 三、项目结构

```
traffic-agent/
├── AGENTS.md                  # ← 本文件
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口 + lifespan
│   │   ├── api/routes.py      # REST + SSE 端点
│   │   ├── core/
│   │   │   ├── config.py      # Settings (Ollama URL, model, paths)
│   │   │   └── state.py       # 全局状态（取消标记）
│   │   ├── models/schemas.py  # Pydantic models (TrafficRecord 等)
│   │   ├── graph/
│   │   │   ├── state.py       # GraphState TypedDict
│   │   │   ├── nodes.py       # supervisor + 4 workers (rag/generate/eval/identity)
│   │   │   └── workflow.py    # build_graph() → StateGraph 编译
│   │   ├── services/
│   │   │   ├── langchain_service.py  # LLM 封装 + with_structured_output
│   │   │   ├── generator.py          # 生成逻辑 + 质量评分 + 导出
│   │   │   ├── graph_runner.py       # astream_events 封装 + SSE 事件
│   │   │   ├── quality_validator.py  # Pandera TrafficFormatSchema + TrafficBusinessSchema
│   │   │   └── report_service.py     # HTML + ECharts 报表
│   │   └── db/database.py     # SQLite CRUD
│   ├── data/
│   │   ├── examples/*.json    # 12 行业 RAG 示例
│   │   └── outputs/           # 生成文件导出目录
│   ├── tests/                 # pytest 测试
│   ├── requirements.txt
│   └── langgraph.json
├── frontend/
│   └── src/
│       ├── api/               # axios + SSE client
│       ├── stores/            # Pinia stores (generation, history)
│       ├── components/        # Vue SFC
│       └── App.vue
├── docs/
│   ├── ROADMAP.md             # 路线图 + 待办事项（权威文档）
│   ├── 开发设计文档_v2.0.md    # 详细后端架构（面试用）
│   ├── Agent核心技术落地.md    # Agent 技术深度文档
│   └── 流量字段枚举.md         # TrafficRecord 字段 + Pandera 规则
├── desc.md                    # 简历技术栈描述
└── resume.md                  # 简历项目描述
```

## 四、开发工作流（Superpowers 技能体系）

### 4.1 技能优先级

本项目已配置 `superpowers` 技能包（14 个子技能），位于 `.qcoder/skills/superpowers/`。**所有开发任务必须优先检查是否有对应技能适用。**

技能优先级规则（来自 `using-superpowers`）：
1. **User 显式指令**（本文件、用户直接请求）— 最高优先级
2. **Superpowers 技能** — 覆盖默认系统行为
3. **默认系统 prompt** — 最低优先级

### 4.2 核心工作流技能

| 阶段 | 技能 | 何时使用 |
|------|------|---------|
| **规划** | `writing-plans` | 复杂任务开始前，先写计划 |
| **头脑风暴** | `brainstorming` | 进入 Plan Mode 前、需求不明确时 |
| **实现** | `subagent-driven-development` | 有计划且任务独立时，逐任务分派子 Agent |
| **实现（并行）** | `executing-plans` | 任务可完全并行时，开独立 Session |
| **调试** | `systematic-debugging` | 任何 bug、测试失败、异常行为，**修复前必须先找根因** |
| **TDD** | `test-driven-development` | 新增功能或修 bug 时，先写失败测试 |
| **代码审查** | `requesting-code-review` | 每个任务完成后、合并前 |
| | `receiving-code-review` | 收到审查反馈时 |
| **并行** | `dispatching-parallel-agents` | 2+ 独立问题域可同时处理时 |
| **收尾** | `finishing-a-development-branch` | 所有任务完成后，合并前 |
| **验证** | `verification-before-completion` | **任何完成声明前，必须运行验证命令并确认输出** |

### 4.3 关键原则

- **证据优先于断言**：没有运行验证命令，不得声称"已完成"或"通过了"（`verification-before-completion`）
- **先找根因再修复**：不允许症状级修补，必须完成 Phase 1 调查后才能提议修复（`systematic-debugging`）
- **子 Agent 全新上下文**：每个子 Agent 只获得其任务所需的确切上下文，不继承主 session 历史（`subagent-driven-development`）
- **两次审查**：实现完成后 → 先 spec 合规审查 → 再代码质量审查 → 两个都通过才算完成（`subagent-driven-development`）

## 五、开发约定

### 5.1 Git

- **Commit message**: 英文，格式 `<type>: <description>`
  - `feat:` 新功能
  - `fix:` 修复
  - `docs:` 文档
  - `refactor:` 重构
  - `test:` 测试
- **禁止** `--no-verify`、`--force` 推送到 main
- **禁止** 修改 git config
- **只在用户明确要求时提交**，不主动 commit

### 5.2 测试

- 框架：pytest
- 运行：`cd backend && python -m pytest tests/ -v`
- **后端改动必须跑全栈集成测试**（`test_routes.py`）
- 修改 `nodes.py` / `workflow.py` 后必须跑 `test_nodes.py` / `test_graph_runner.py`
- 修改 `generator.py` / `quality_validator.py` 后必须跑 `test_quality_evaluator.py` / `test_generator_industries.py`
- 覆盖率目标：核心路径 100%，整体 > 80%

### 5.3 代码风格

- Python：类型注解必须（TypedDict / Pydantic models）
- Vue：Composition API + `<script setup lang="ts">`
- 注释用中文（特殊业务逻辑）或英文（通用逻辑）
- 禁止创建无意义的 `.md` / 临时文件

### 5.4 后端架构约束

- **不要**在 `nodes.py` 中直接操作数据库，通过 `db/database.py`
- **不要**在 `routes.py` 中写业务逻辑，通过 `services/`
- Graph 节点签名：`async def xxx_node(state: GraphState) -> GraphState`
- Supervisor 节点返回 `Command[Literal[...]]`，conditional edge 返回 `str | list[Send]`

## 六、常用命令

```powershell
# 后端
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend
npm run dev

# 测试
cd backend
python -m pytest tests/ -v
python -m pytest tests/test_nodes.py -v
python -m pytest tests/test_routes.py -v

# 清理
cd backend
python cleanup.py
```

## 七、当前状态

- **已完成**：P1 核心生成流水线 → P2 Supervisor-Worker 架构 → P3 SSE 思考链 + LangSmith 追踪
- **下一任务**：参考 `docs/ROADMAP.md` 第七章优先级总览
- **设计文档**：`docs/开发设计文档_v2.0.md`（面试级详细架构）
- **技术深度**：`docs/Agent核心技术落地.md`
