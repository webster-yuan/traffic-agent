# Traffic Agent 路线图与下一步指引

**更新**: 2026-05-03
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
| 测试 | 66 个 pytest | 质量评估 13 专项 + 路由/生成/并发/取消/导出/回放 |
| 清理 | 定期文件清理 | `cleanup_schedule.py`，30 天过期 |
| 检查点回放 | 任意节点状态回放 | `aget_state_history()` + Fork Replay，支持 hint override |
| **Supervisor-Worker** | **多智能体编排引擎** | LLM 驱动 Supervisor 动态路由 + RAG/Generate/Eval/Identity/Approval 五 Worker |
| **Custom Streaming** | **SSE 阶段流 + 思考链** | `stream_mode=["updates","custom"]` + `get_stream_writer()` 实时推送阶段/思考事件 |
| **Human-in-the-Loop** | **人工审核中断放行** | LangGraph `interrupt()` 暂停图 + `POST /resume` 恢复 + 前端审批面板 |

---

## 三、剩余待处理项（按价值排序）

### 3.1 🟡 报表 PDF 导出 — 业务交付刚需

**当前状态**: 报表在新标签打开 HTML，用户手动 Ctrl+P 打印。

**为什么值得做**:
- 离线分享：发给不接触系统的同事/客户，PDF 是通用格式
- 会议场景：周报/月报，ECharts 图表嵌入 PDF 直观展示数据质量趋势
- 合规归档：安全审计需要可追溯的 PDF 质量报告

**技术路径**:

| 方案 | 依赖 | 优点 | 缺点 |
|------|------|------|------|
| **WeasyPrint** | `weasyprint` (~5MB) | 纯 Python，轻量，HTML→PDF 一行代码 | ECharts 是 JS 渲染的 SVG，WeasyPrint 不执行 JS，图表会丢失 |
| **Playwright headless** | `playwright` + Chromium (~150MB) | 完整浏览器渲染，ECharts 截图完美还原 | Chromium 体积大，安装慢；首次渲染有额外延迟 |
| **后端预渲染静态截图** | 当前 ECharts 数据 → matplotlib/seaborn 静态图 | 无浏览器依赖，PDF 体积小 | 图表美观度不如 ECharts，需要额外维护两套图表代码 |

**推荐**: 如果 PDF 是"偶尔用一两次"，**WeasyPrint**（图表位置显示数据摘要表格）。如果 PDF 是"周报核心交付物"，**Playwright headless** 才能真正还原 ECharts 可视化效果。

---

### 3.2 ✅ Human-in-the-Loop 人工审批 — 已实现

**实现**: LangGraph `interrupt()` 在 `approval_worker` 中暂停图执行，前端通过 SSE `waiting_for_approval` 事件展示审批面板（统计摘要 + 样例记录），用户 Approve/Reject 后调用 `POST /resume/{session_id}` 恢复执行。

**关键修复**:
- LangGraph `astream()` 压制 `GraphInterrupt` 并以 `updates` 事件 `{"__interrupt__": ...}` 形式抛出 → SSE handler 检测 `__interrupt__` 并发射 `waiting_for_approval`
- Supervisor 增加 LLM 前确定性路由检查，确保审批节点不被 LLM 跳过
- Reject → regenerate 循环通过 `generate_worker` 重置 `approval_action` 避免无限循环

### 3.3 🟡 取消不能立即中断 LLM — 体验已知限制

**根本原因**: 取消只设置内存标记，但 LLM 调用期间（耗时最长）标记无法被检查。当前 `interrupt()` 已用于 HITL 审批，不适用于任意取消场景。

**当前缓解**: 节点入口 `_check_cancelled()` 检查，LLM 返回后立即识别取消。等待时间 = 当前 LLM 调用剩余时长（10-60s）。

---

### 3.4 🟢 移动端适配 — 管理端触达

**当前**: CSS Grid `1fr 400px` 双栏，小屏出现横向滚动。

**技术**: `@media (max-width: 768px)` → 单栏 `grid-template-columns: 1fr`，表单/表格折叠。

**业务价值**: 手机上快速查看生成状态和历史记录，不需要完整交互。

---

### 3.5 🟢 低优先级技术债

| 项目 | 说明 | 建议 |
|------|------|------|
| `/generate` sync 端点冗余 | 与 `/generate/stream` 逻辑重复 60 行 | 保留兼容，标记 deprecated |
| `on_event("startup")` 已 deprecated | FastAPI 推荐 lifespan context manager | ✅ 已修复 (v2.3) |
| API 鉴权缺失 | CORS `*`，无 token | Docker 部署时加 API Key / JWT |

---

## 四、技术演进路线

### 4.1 下一阶段：Docker 化（需 Windows 11 + Docker Desktop）

**为什么需要这一步**: 当前 SQLite + `asyncio.create_task` 组合在单机单用户场景够用，但存在硬天花板：
- SQLite 写锁：并发 > 3 任务时写入冲突概率上升
- 任务无持久化：服务重启丢失所有进行中的任务
- 无监控：出问题只能看日志，没有面板

| 层 | 当前 | Docker 后 | 业务价值 |
|----|------|-----------|---------|
| 数据库 | SQLite 文件 | PostgreSQL 容器 | 并发写入无锁，JSONB 存储流量记录支持复杂查询 |
| 任务队列 | `asyncio.create_task` | Celery + Redis | 任务持久化、失败自动重试、优先级调度 |
| 缓存 | 无 | Redis | 会话进度缓存，减少 DB 查询 |
| 对象存储 | 本地 `data/outputs/` | MinIO 容器 | 文件版本管理 + 生命周期自动过期 |
| 部署 | 手动 `uvicorn` + `vite` | `docker-compose up` | 一键全栈启动 |
| 监控 | 本地 `error.log` | Prometheus + Grafana | 面板展示吞吐量/延迟/错误率 |

**迁移步骤**（技术指引）:
1. 现有 SQL 改为 SQLAlchemy ORM（不改业务逻辑，只换数据访问层）
2. `docker-compose.yml` 定义 5 个服务（PostgreSQL + Redis + MinIO + backend + frontend）
3. Celery 替换 `asyncio.create_task`，`routes.py` 中 `create_task()` → `celery_app.send_task()`
4. Grafana Dashboard 导入预置模板（生成速率 / 质量趋势 / 错误分布）

### 4.2 远期：平台化

**前置条件**: Docker 化完成

| 能力 | 技术 | 业务价值 |
|------|------|---------|
| 多模型对比 | 同一场景用 Ollama / 云端 API 分别生成 | 评估不同模型的数据质量和风格偏差 |
| LangSmith 回归评估 | Dataset + Evaluator 自动评分 | 每次改 prompt / schema 后跑回归，防止退化 |
| 模板管理 | 行业 → 场景 → 异常模式 三层模板 | 常用场景一键复用，减少重复配置 |
| Prompt 版本管理 | Git-like prompt 版本 + A/B 测试 | 安全地迭代 prompt，可回滚 |
| 多用户 + RBAC | JWT 鉴权 + 角色管理 | 团队协作，按角色限制操作 |
| 定时批量 | Celery Beat + Cron | 每日自动生成 + 自动导出周报 PDF |

---

## 五、运行约束（非代码缺陷）

### 5.1 v2.3 代码审查整改 (2026-05-04)

基于 `docs/review.md` 全项目审查报告，完成以下修复：

| 级别 | 修复项 | 状态 |
|------|--------|------|
| 🔴 C1 | CORS 限制具体 origin（`settings.cors_origins`） | ✅ |
| 🔴 C2 | `TrafficGenerateResponse.quality_score` → `QualityScore \| None` | ✅ |
| 🔴 C3 | `_check_cancelled` 提取到 `app/graph/shared.py` | ✅ |
| 🔴 C4 | `_dedupe_notes` 提取到 `app/core/utils.py` | ✅ |
| 🔴 C5 | `_fix_json` 提取到 `app/core/json_utils.py` | ✅ |
| 🔴 C6 | 数据库连接 `atexit.register` 清理 | ✅ |
| 🟠 I7 | `nodes.py` 添加 DEPRECATED 注释 | ✅ |
| 🟠 I9 | `on_event("startup")` → `lifespan` | ✅ |
| 🟠 I11 | 异常传播 → `HTTPException(500)` | ✅ |
| 🟠 I13 | `date_from`/`date_to` → `date` 类型 Pydantic 校验 | ✅ |
| 🟠 I14 | `ChatOllama` 抽取到 `app/services/llm_factory.py` | ✅ |
| 🟠 I15 | `approval_hint` 合并到 `eval_feedback` 传入子图 | ✅ |

## 五、运行约束（非代码缺陷）

以下问题源于本地 Ollama + qwen2.5:7b 模型能力限制，不是代码问题：

- LLM 单条生成 2-5s — 模型升级后自然改善
- 大批量（100+ 条）OOM 风险 — 模型升级 + Celery 任务队列后分流
- SQLite 并发写锁 — Docker + PostgreSQL 后解决

---

## 六、LangGraph Agent 深度提升

以下 3 项从 LangGraph 能力深度出发：

| # | 任务 | 说明 | 改动量 | 状态 |
|---|------|------|--------|------|
| 🟡 1 | **真 RAG 向量检索** | 当前 `rag_worker` 读静态 JSON，改为 ChromaDB 嵌入式向量库，成功案例自动入库，语义相似度检索 | ~150 行 | 📋 待办（暂缓） |
| 🟡 2 | **质量重试硬上限 + 降级策略** | qwen2.5:7b 质量评分偏低导致无限重试 → Supervisor 增加降级路由：3 次不通过后切换宽松阈值或标记 "best effort" | ~40 行 | 📋 待办（暂缓） |
| 🟢 3 | **Prompt 自优化反馈闭环 ✅** | eval 返回不合格字段明细 → generate 读取后动态调整 prompt，形成自我改进循环 | ~60 行 | ✅ 已完成 |

### 6.1 ✅ 已完成的 LangGraph 深度能力

| # | 任务 | 核心技术点 |
|---|------|-----------|
| 6 | **Prompt 自优化反馈闭环** | eval 失败 → `eval_feedback` → generate subgraph `prepare_prompt_node` 注入改进指引 → 自我校正 |
| 1 | **Supervisor-Worker 多智能体架构** | LLM 结构化输出 (`RouterDecision`) + `Send()` 并行扇出 + Generate 子图嵌套 |
| 2 | **Custom Streaming 思考链** | `stream_mode=["updates","custom"]` + `get_stream_writer()` + SSE 阶段/进度/思考事件 |
| 3 | **Human-in-the-Loop 审批** | LangGraph `interrupt()` 动态中断 + `graph.ainvoke(Command(resume=...))` 恢复 + 前端审批面板 |
| 4 | **检查点回放 (Time Travel)** | `aget_state_history()` + Fork Replay + hint override 参数注入 |
| 5 | **AsyncSqliteSaver 持久化** | SQLite 异步 checkpoint + `thread_id` 指针管理 + 跨会话状态恢复 |

---

## 七、任务优先级总览

```
当前可做（无需环境升级）:
  1. 🟡 报表 PDF 导出                   ← 业务交付最高价值
  2. 🟢 移动端 @media 适配              ← 5 分钟 quick win
  3. 🟢 lifespan → on_event            ← 消除 deprecation warning

📋 已确认，近期不做:
  4. 🟡 真 RAG 向量检索 (ChromaDB)
  5. 🟡 质量重试硬上限 + 降级策略

✅ 已完成:
  6. 🟢 Prompt 自优化反馈闭环 ✅
  7. 🟡 Human-in-the-Loop 人工审批 ✅
  8. 🟡 Custom Streaming 思考链 ✅

需要环境升级:
  7. Windows 11 + Docker Desktop
  8. SQLAlchemy ORM + PostgreSQL
  9. Celery + Redis 任务队列

远期:
 10. 多模型对比 + LangSmith 回归
 11. 模板 + Prompt 版本管理
```
