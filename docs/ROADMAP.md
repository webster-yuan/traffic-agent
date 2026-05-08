# Traffic Agent 路线图与下一步指引

**更新**: 2026-05-07  | **审查整改**: 2026-05-04  | **v3.1**: Token 追踪/模型信息/批量重试/中文修复/布局优化
**技术栈**: FastAPI + LangGraph + SQLite + Vue 3 + Pinia + Vite + Ollama (qwen2.5:7b)
**环境**: Windows 10 + PowerShell + Ollama 本地

---

## 一、项目架构

```
用户浏览器 (Vue 3 + Pinia + Vite)
    │  SSE Stream / REST API
    ▼
FastAPI (uvicorn, port 8000)
    │
    ├── routes.py           API 端点（生成/历史/下载/报表/批量/回放）
    ├── session_service     SQLite CRUD + 批量任务状态
    ├── generator.py        LLM 调用（async）+ 质量评分 + CSV/JSON/Parquet
    ├── quality_validator   Pandera 声明式 schema（15 校验规则）
    ├── report_service      HTML 报表（含 ECharts 图表）
    │
    ▼
LangGraph 工作流（supervisor.py + workers.py + workflow.py）
    │
    ├── supervisor_node    LLM 驱动的主控路由器（RouterDecision 结构化输出）
    ├── rag_worker         行业场景推断 + 12 套 JSON 示例注入
    ├── generate_worker    async LLM 流量生成（嵌套子图）
    ├── eval_worker        三维度质量评分 + Pandera 字段/业务校验
    ├── approval_worker    Human-in-the-Loop 中断审批（interrupt()）
    └── identity_worker    身份标签校验（full 模式）
        │
        ▼
LangSmith Tracing（traceable 装饰器）
SQLite（traffic_sessions / batch_sessions / batch_tasks）
```

---

## 二、已完成的能力矩阵

| 模块 | 能力 | 技术要点 |
|------|------|---------|
| 生成引擎 | LangGraph 四阶段流水线 | RAG → 生成 → 评估 → 身份校验 |
| RAG | 12 行业专属示例注入 | `data/examples/*.json`，3 条/行业，注入 system prompt |
| 异步 LLM | async + 超时保护 | `asyncio.wait_for(llm.ainvoke(), timeout=300)` |
| 质量评估 | 三维度 + Pandera 声明式校验 | `TrafficFormatSchema`（13 字段）+ `TrafficBusinessSchema`（6 跨字段规则） |
| 导出 | CSV / JSON / Parquet 多格式 | Parquet 使用 Snappy 压缩，同会话侧车文件 |
| 报表 | HTML + ECharts 四图表 | 雷达图（质量维度）/ 饼图（方法分布）/ 柱状图（状态码分布） |
| 批量 | 最多 10 任务并发 | 独立会话 + 2 秒轮询 + `asyncio.Semaphore(3)` |
| 历史 | 服务端 7 维筛选 + 分页 | SQLite 动态 WHERE，20 条/页 |
| 前端 UI | Tab 导航 + 虚拟滚动 + 响应式 | CSS Grid + `content-visibility:auto` + 粘性表头 |
| 测试 | 229 个 pytest | 质量评估/路由/生成/并发/取消/导出/回放/Token/Prompt/可观测性 |
| 清理 | 定期文件清理 | `cleanup_schedule.py`，30 天过期 |
| 检查点回放 | 任意节点状态回放 | `aget_state_history()` + Fork Replay，支持 hint override |
| **Supervisor-Worker** | **多智能体编排引擎** | LLM 驱动 Supervisor 动态路由 + RAG/Generate/Eval/Identity/Approval 五 Worker |
| **Custom Streaming** | **SSE 阶段流 + 思考链** | `stream_mode=["updates","custom"]` + `get_stream_writer()` 实时推送阶段/思考事件 |
| **Human-in-the-Loop** | **人工审核中断放行** | LangGraph `interrupt()` 暂停图 + `POST /resume` 恢复 + 前端审批面板 |
| **v3.1: Token 消耗追踪** | **SSE token_usage 事件 + 前端统计面板** | `token_counter.py` `extract_from_response()` 提取 Ollama token 元数据 |
| **v3.1: 模型信息展示** | **GET /model-info + 前端模型徽章** | 返回 model_name/provider/context_window/capabilities |
| **v3.1: 批量失败重试** | **一键重试 + 前端按钮** | `POST /batch/{id}/retry-failed` + `trafficStore.retryFailedBatchTasks()` |
| **v3.1: 中文编码修复** | **SSE 消息乱码消除** | supervisor.py/workers.py UTF-8 修复 + STAGE_NAME `approval` 补充 |

---

## 五、运行约束（非代码缺陷）

### 5.1 v2.4 代码审查整改 (2026-05-04)

基于 `docs/review.md` 全项目审查报告 v1.0 + v2.0，完成以下修复：

**v1.0 审查关闭（13 项）**：

| 级别 | 修复项 | 状态 |
|------|--------|------|
| 🔴 C1 | CORS 限制具体 origin（`settings.cors_origins`） | ✅ |
| 🔴 C2 | `TrafficGenerateResponse.quality_score` → `QualityScore \| None` | ✅ |
| 🔴 C3 | `_check_cancelled` 提取到 `app/graph/shared.py` | ✅ |
| 🔴 C4 | `_dedupe_notes` 提取到 `app/core/utils.py` | ✅ |
| 🔴 C5 | `_fix_json` 提取到 `app/core/json_utils.py` | ✅ |
| 🔴 C6 | 数据库连接 `atexit.register` 清理 | ✅ |
| 🟠 I7 | `nodes.py` 标记 DEPRECATED → **已删除** | ✅ |
| 🟠 I9 | `on_event("startup")` → `lifespan` | ✅ |
| 🟠 I11 | 异常传播 → `HTTPException(500)` | ✅ |
| 🟠 I13 | `date_from`/`date_to` → `date` 类型 Pydantic 校验 | ✅ |
| 🟠 I14 | `ChatOllama` 抽取到 `app/services/llm_factory.py` | ✅ |
| 🟠 I15 | `approval_hint` 合并到 `eval_feedback` 传入子图 | ✅ |
| 🟠 I8 | 行业映射统一到 `app/data/industries.py` 单一数据源，前后端共享 API | ✅ |

**v2.0 审查关闭（9 项）**：

| 级别 | 修复项 | 状态 |
|------|--------|------|
| 🔴 P0-1 | API 速率限制（slowapi `SlowAPIMiddleware`，200/day） | ✅ |
| 🔴 P0-2 | 全链路 Request ID 中间件（`X-Request-ID` header） | ✅ |
| 🟠 P1-1 | 删除废弃 `nodes.py`（170 行死代码） | ✅ |
| 🟠 P1-2 | `_random_body` 收归 `IndustryConfig.body_template` 声明式模板 | ✅ |
| 🟢 P2-1 | 日志语言统一为英文（routes/generator/workers ~20 处） | ✅ |
| 🟢 P2-2 | `langchain_service.py` 迁移到 `llm_factory.get_ollama_llm()` | ✅ |
| 🟢 P2-3 | `GraphState` 字段按逻辑分组（7 组注释） | ✅ |
| 🟢 P2-4 | Checkpoint 列表分页（`limit` + `before` cursor） | ✅ |
| 🟢 P2-5 | Approval Worker 示例记录扩展 `rtt`/`duration` 字段 | ✅ |
| 🟢 P2-6 | `trafficStore.ts` HITL 去重（`_handleResume()` 提取） | ✅ |
| 🟢 P2-7 | 前端 Industries API 加载失败降级（`FALLBACK_INDUSTRIES` 静态列表） | ✅ |

| 🟠 I12 | aiosqlite 迁移 — `database.py` 从 sync `sqlite3` + thread-local 迁移到 `aiosqlite` async 连接 | ✅ |
| 🟠 P1-3 | `test_batch.py`/`test_routes.py`/`test_observability_routes.py` 同步 mock → `AsyncMock` | ✅ |

**待处理**：P1-4（routes.py 拆分）

以下问题源于本地 Ollama + qwen2.5:7b 模型能力限制，不是代码问题：

- LLM 单条生成 2-5s — 模型升级后自然改善
- 大批量（100+ 条）OOM 风险 — 模型升级 + Celery 任务队列后分流
- SQLite 并发写锁 — Docker + PostgreSQL 后解决

---

---
