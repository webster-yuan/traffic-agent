# Traffic Agent 待办事项与路线图

**更新日期**: 2026-04-29
**当前技术栈**: FastAPI + LangGraph + SQLite + Vue 3 + Pinia + Vite + Ollama (本地)
**环境**: Windows 10 + PowerShell + Ollama (qwen2.5:7b)

---

## 当前项目状态（截至 2026-04-29）

### 已完成的能力矩阵

| 模块 | 功能 | 状态 |
|------|------|------|
| 生成引擎 | LangGraph 四阶段流水线（RAG → 生成 → 评估 → 身份校验） | ✅ |
| 追踪 | LangSmith Trace 集成 + session_id/thread_id 关联 | ✅ |
| 前端 | 阶段时间线 + 进度可视化 + 取消任务 + 错误重试 | ✅ |
| 历史 | 高级筛选（关键字/行业/阶段/状态/日期/评分）、下载、删除 | ✅ |
| 行业 | 11 个行业场景（government ~ gaming）+ 自动场景推断 | ✅ |
| 质量 | 三维度评分 + Pandera 声明式 schema（TrafficFormatSchema 13 字段校验 + TrafficBusinessSchema 6 跨字段业务规则）| ✅ |
| 导出 | CSV / JSON / Parquet 多格式（同会话侧车文件） | ✅ |
| 报表 | HTML 报表 + ECharts 雷达图/饼图/柱状图 | ✅ |
| 批量 | 批量生成（最多 10 任务、独立会话、2 秒轮询） | ✅ |
| 并发 | asyncio.Semaphore(3) 并发控制 + 任务取消 | ✅ |
| 构建 | Vite 代码分割（vue/pinia 独立 chunk） | ✅ |
| 数据库 | SQLite threading.local() 连接池 | ✅ |
| 清理 | 定期文件清理 (cleanup_schedule.py, 30 天) | ✅ |
| 测试 | 55 个 pytest 测试覆盖核心模块 + 13 个质量评估专项测试 | ✅ |

### 运行约束（非代码问题，不列入后端缺陷）

- 本地 Ollama + qwen2.5:7b 模型能力有限，单条生成 2-5 秒
- Windows 10 环境，无 Docker
- 当前阶段聚焦功能完善，性能优化在模型升级后处理

---

## 一、前端问题（需修复）

### 1.1 响应式布局 ✅（2026-04-29）

### 1.2 历史记录无分页 ✅（2026-04-29）

### 1.3 历史筛选服务端化 ✅（2026-04-29）

**已实现**: `GET /history` 端点接受 7 个可选筛选参数 (`keyword`/`industry`/`stage`/`status`/`date_from`/`date_to`/`min_quality`)，后端 SQLite 动态 WHERE 查询。前端 `filteredHistory` getter 已移除，筛选变更自动请求服务端并重置分页。

### 1.4 无虚拟滚动 ✅（2026-04-29）

**已实现**: 纯 CSS 方案，无需引入第三方库。`.history-table-wrap` 容器 `max-height:55vh; overflow-y:auto` 限定可视区域，`thead position:sticky; top:0` 粘性表头，`tbody tr content-visibility:auto` 浏览器原生跳过屏外渲染。配合服务端分页（20 条/页），DOM 节点始终受控。

### 1.5 报表仅支持新标签打开 🟡

**当前问题**: 报表链接 `<a target="_blank">` 在新标签打开 HTML。无法直接导出为 PDF。
**影响**: 用户需手动 Ctrl+P 打印为 PDF。
**建议**: 后端加 `?format=pdf` 参数，用 `weasyprint` 或浏览器 headless 生成 PDF。

### 1.6 UI 导航结构单薄 ✅（2026-04-29）

---

## 二、后端问题（需修复）

### 2.1 RAG 阶段升级 ✅（2026-04-29）

**方案 A（静态示例）已实现**: `_get_examples(industry)` 从 `data/examples/{industry}.json` 加载行业专属示例，不存在时回退 `custom.json`。12 个行业各有 3 条示例（2 real + 1 fake），注入到 LLM system prompt 的 `参考样例` 字段。

**位置**:
- `backend/app/services/generator.py:141-149` — `_get_examples(industry)` 读 JSON
- `backend/app/graph/nodes.py:88-91` — `rag_node` 记录示例来源
- `backend/data/examples/` — 12 个行业 JSON 文件

### 2.2 LLM 调用异步化 + 超时保护 ✅（2026-05-01）

**已实现**: `generate_records_by_llm()` 改为 `async def`，`llm.invoke()` → `await asyncio.wait_for(llm.ainvoke(), timeout=...)`。`generate_node` 也改为 `async def`。LangGraph 原生支持异步节点，对 `graph.invoke()` 和 `graph.ainvoke()` 均透明。

**位置**:
- `backend/app/services/generator.py:156-210` — `async def generate_records_by_llm` + `asyncio.wait_for`
- `backend/app/graph/nodes.py:100-114` — `async def generate_node` + `await generate_records_by_llm`

### 2.3 取消操作不能立即中断 Graph 执行 🟡

**位置**: `backend/app/core/state.py` + `backend/app/graph/nodes.py:23-26`

**问题**: 取消只设置内存标记，Graph 节点在每次 entry 检查 `is_cancelled()`。但如果 LLM 正在 `invoke()`（耗时最长的步骤），取消标志无法被检查到，需要等 LLM 返回。
**影响**: 用户点击取消后，可能需要等待 10-60 秒才能真正终止。
**建议**: 短期无法解决（LangGraph 节点的同步 LLM 调用不可中断），记录为已知限制。

### 2.4 industry 字段无枚举校验 🟡 → ✅

**位置**: `backend/app/models/schemas.py:22`

**问题**: `industry` 接受任意字符串。
**状态**: ✅ 已修复（2026-04-29）— 定义 `Industry = Literal[12个行业名]`，Pydantic 自动校验，输入 `"asdf"` 会返回清晰错误。

### 2.5 同步 /generate 端点阻塞事件循环 🟢

**位置**: `backend/app/api/routes.py:55-108`

**问题**: `POST /generate` 是同步端点，`run_generation_graph()` 直接阻塞整个请求直到 LLM 返回。
**影响**: 已不推荐使用，前端默认走 `/generate/stream` 流式端点。保留仅用于 API 兼容。
**建议**: 低优先级，保留或标记为 deprecated。

### 2.6 无 API 鉴权 🟢

**位置**: `backend/app/main.py:9-15`

**问题**: CORS `allow_origins=["*"]`，无任何身份验证。
**影响**: 纯本地开发无影响。未来部署公网/内网时需要。
**建议**: 后续 Docker 部署时加 API Key 或 JWT 鉴权。

---

## 三、架构演进路线

### 3.1 当前阶段：功能完善（现在）

1. ~~RAG 升级（方案 A：静态示例文件）~~ ✅
2. ~~历史筛选服务端化~~ ✅
3. ~~虚拟滚动（CSS content-visibility + sticky thead）~~ ✅
4. ~~异步 LLM 调用 + asyncio.wait_for 超时~~ ✅
5. ~~数据质量深化（字段合法性 + 业务一致性 + 异常标签准确性）~~ ✅
6. ~~Pandera 结构化校验流水线~~ ✅

**位置**:
- `backend/app/services/quality_validator.py` — Pandera schemas（TrafficFormatSchema / TrafficBusinessSchema）
- `backend/app/services/generator.py:317-324` — `_score_format` / `_score_business` 改为委托 Pandera
- `backend/tests/test_quality_evaluator.py` — 13 个专项测试全部通过

### 3.2 下一阶段：环境升级 → Docker

**前置条件**: 升级 Windows 11 + 安装 Docker Desktop

| 升级项 | 当前 | Docker 后 |
|--------|------|-----------|
| 数据库 | SQLite 文件 | PostgreSQL 容器（持久化 + 并发） |
| 缓存 | 无 | Redis 容器（任务队列、进度缓存） |
| 任务队列 | asyncio.create_task | Celery + Redis（持久化任务、失败重试） |
| 对象存储 | 本地 data/outputs/ | MinIO 容器（版本管理、生命周期） |
| 部署 | uvicorn --reload 手动启动 | docker-compose up（一键全套） |
| 日志 | 本地 error.log | ELK / Loki 容器（聚合查询） |
| 监控 | 无 | Prometheus + Grafana 容器（面板展示） |

### 3.3 远期：平台化

- 多模型对比（Ollama vs 云端 API）
- LangSmith Dataset 回归评估
- 模板管理 + Prompt 版本管理
- 多用户 + RBAC
- 定时批量生成（Cron Job）

---

## 四、当前不处理的项（已明确排除）

以下问题源于本地 Ollama 模型能力限制，不是代码缺陷，在当前 Windows 10 + 低配模型环境下无需处理：

- ❌ LLM 生成速度慢（2-5s/条）→ 模型升级后自然解决
- ❌ 高并发性能瓶颈 → Docker + Celery + PostgreSQL 后解决
- ❌ 大批量生成（100+ 条）内存 → 模型升级 + 任务队列后解决
- ❌ SQLite 并发写入锁 → Docker + PostgreSQL 后解决
- ❌ 日志轮转/生产部署配置 → Docker 化后统一配置

---

## 五、成功指标

### 功能
- [x] 11 行业 + 批量 + 导出 + 报表
- [x] 响应式布局适配
- [x] 历史分页可用
- [x] Tab 导航切换
- [x] industry 枚举校验
- [x] RAG 提供真实行业示例

### 体验
- [x] 流式进度 + 阶段时间线
- [x] 错误卡片 + 重试
- [ ] 移动端可用

### 架构
- [ ] Docker 化部署
- [ ] PostgreSQL 迁移
- [ ] Redis 缓存 + Celery 任务队列
