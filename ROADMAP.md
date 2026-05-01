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
| 质量 | 三维度评分（格式 30% + 业务 40% + 多样性 30%）+ 扣分说明 | ✅ |
| 导出 | CSV / JSON / Parquet 多格式（同会话侧车文件） | ✅ |
| 报表 | HTML 报表 + ECharts 雷达图/饼图/柱状图 | ✅ |
| 批量 | 批量生成（最多 10 任务、独立会话、2 秒轮询） | ✅ |
| 并发 | asyncio.Semaphore(3) 并发控制 + 任务取消 | ✅ |
| 构建 | Vite 代码分割（vue/pinia 独立 chunk） | ✅ |
| 数据库 | SQLite threading.local() 连接池 | ✅ |
| 清理 | 定期文件清理 (cleanup_schedule.py, 30 天) | ✅ |
| 测试 | 14 个 pytest 测试覆盖核心模块 | ✅ |

### 运行约束（非代码问题，不列入后端缺陷）

- 本地 Ollama + qwen2.5:7b 模型能力有限，单条生成 2-5 秒
- Windows 10 环境，无 Docker
- 当前阶段聚焦功能完善，性能优化在模型升级后处理

---

## 一、前端问题（需修复）

### 1.1 响应式布局 ✅（2026-04-29）

### 1.2 历史记录无分页 ✅（2026-04-29）

### 1.3 历史筛选纯前端实现 🔴

**当前问题**: 所有筛选逻辑在 `trafficStore.filteredHistory` getter 中做客户端过滤。数据量大时每次都需拉全量数据到前端。
**影响**: 记录多后前端卡顿。
**建议**: 低优先级（当前数据量 < 100 条无感知），未来加后端筛选接口。

### 1.4 无虚拟滚动 🟡

**当前问题**: 历史记录列表全量渲染到 DOM，没有虚拟滚动。
**影响**: 记录超过数百条时渲染性能下降。
**建议**: 引入 `vue-virtual-scroller`。

### 1.5 报表仅支持新标签打开 🟡

**当前问题**: 报表链接 `<a target="_blank">` 在新标签打开 HTML。无法直接导出为 PDF。
**影响**: 用户需手动 Ctrl+P 打印为 PDF。
**建议**: 后端加 `?format=pdf` 参数，用 `weasyprint` 或浏览器 headless 生成 PDF。

### 1.6 UI 导航结构单薄 ✅（2026-04-29）

---

## 二、后端问题（需修复）

### 2.1 RAG 阶段仍是 Mock 🔴

**位置**: `backend/app/graph/nodes.py:84-97`

```python
def rag_node(state: GraphState) -> GraphState:
    state["scenario"] = infer_scenario(state["industry"])
    state["retrieved_cases"] = [
        {"industry": state["industry"], "scenario": state["scenario"], "content": "mock_case"}
    ]
```

**问题**: 场景推断是硬编码字典映射，检索结果是写死的 `mock_case`。没有真正的知识库检索，无法为 LLM 提供行业相关的真实流量案例作为 few-shot。
**影响**: LLM 生成质量依赖 prompt 中的示例（目前只有 2 条电商硬编码示例），跨行业泛化能力弱。
**建议**: 
- 方案 A（轻量）：为每个行业维护一个示例 JSON 文件，检索时加载。
- 方案 B（完整）：用 Chroma/FAISS 做向量检索，把行业特征文档索引化。

### 2.2 LLM 调用未做超时/重试包装 🟡

**位置**: `backend/app/services/generator.py:231-238`

```python
llm = ChatOllama(...)
response = llm.invoke(f"{system_prompt}\n\n请生成流量数据")
```

**问题**: `llm.invoke()` 是同步调用，在 LangGraph 节点中直接执行。Ollama 本地模型响应慢（2-5s/call）时，事件循环被阻塞。也没有 try/except 处理 LLM 调用本身的网络错误、超时。
**影响**: 当前 Ollama 本地部署不会网络超时，但模型卡死时整个请求挂起。将来换远程 API 时需要此机制。
**建议**: 未来升级到异步 LLM 调用 `llm.ainvoke()` + `asyncio.wait_for()`。

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

1. RAG 升级（方案 A：静态示例文件）
2. 历史筛选服务端化

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
- [ ] RAG 提供真实行业示例

### 体验
- [x] 流式进度 + 阶段时间线
- [x] 错误卡片 + 重试
- [ ] 移动端可用

### 架构
- [ ] Docker 化部署
- [ ] PostgreSQL 迁移
- [ ] Redis 缓存 + Celery 任务队列
