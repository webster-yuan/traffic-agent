# Traffic Agent 路线图与下一步指引

**更新**: 2026-05-01
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
    ├── routes.py           API 端点（生成/历史/下载/报表/批量）
    ├── session_service     SQLite CRUD + 批量任务状态
    ├── generator.py        LLM 调用（async）+ 质量评分 + CSV/JSON/Parquet
    ├── quality_validator   Pandera 声明式 schema（15 校验规则）
    ├── report_service      HTML 报表（含 ECharts 图表）
    │
    ▼
LangGraph 工作流（nodes.py + workflow.py）
    │
    ├── rag_node          行业场景推断 + 12 套 JSON 示例注入
    ├── generate_node     async LLM 流量生成（asyncio.wait_for 超时保护）
    ├── eval_node         三维度质量评分 + Pandera 字段/业务校验
    └── identity_node     身份标签校验（full 模式）
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
| 测试 | 55 个 pytest | 质量评估 13 专项 + 路由/生成/并发/取消/导出 |
| 清理 | 定期文件清理 | `cleanup_schedule.py`，30 天过期 |

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

### 3.2 🟡 取消不能立即中断 LLM — 体验已知限制

**根本原因**: 取消只设置内存标记，但 LLM 调用期间（耗时最长）标记无法被检查。LangGraph 1.x 的 `interrupt()` 是为 human-in-the-loop 设计，不适用于任意取消场景。

**技术约束**: 当前无法在 LangGraph 1.x + syncio 模型下根本解决。升级路径：
- LangGraph 2.x 可能提供原生取消支持
- 或迁到 Celery + Redis 后，worker 进程可直接被 SIGTERM 终止

**当前缓解**: 节点入口 `_check_cancelled()` 检查，LLM 返回后立即识别取消。等待时间 = 当前 LLM 调用剩余时长（10-60s）。

---

### 3.3 🟢 移动端适配 — 管理端触达

**当前**: CSS Grid `1fr 400px` 双栏，小屏出现横向滚动。

**技术**: `@media (max-width: 768px)` → 单栏 `grid-template-columns: 1fr`，表单/表格折叠。

**业务价值**: 手机上快速查看生成状态和历史记录，不需要完整交互。

---

### 3.4 🟢 低优先级技术债

| 项目 | 说明 | 建议 |
|------|------|------|
| `/generate` sync 端点冗余 | 与 `/generate/stream` 逻辑重复 60 行 | 保留兼容，标记 deprecated |
| `on_event("startup")` 已 deprecated | FastAPI 推荐 lifespan context manager | 下次改 `main.py` 时顺手改 |
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

以下问题源于本地 Ollama + qwen2.5:7b 模型能力限制，不是代码问题：

- LLM 单条生成 2-5s — 模型升级后自然改善
- 大批量（100+ 条）OOM 风险 — 模型升级 + Celery 任务队列后分流
- SQLite 并发写锁 — Docker + PostgreSQL 后解决

---

## 六、任务优先级总览

```
当前可做（无需环境升级）:
  1. 🟡 报表 PDF 导出           ← 最高价值剩余项
  2. 🟢 移动端 @media 适配       ← 5 分钟 quick win
  3. 🟢 lifespan → on_event     ← 消除 deprecation warning

需要环境升级:
  4. Windows 11 + Docker Desktop
  5. SQLAlchemy ORM + PostgreSQL
  6. Celery + Redis 任务队列

远期:
  7. 多模型对比 + LangSmith 回归
  8. 模板 + Prompt 版本管理
```
