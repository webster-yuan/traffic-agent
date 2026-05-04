# Traffic Agent — Agent 核心技术落地

> 本文档介绍 Traffic Agent 项目中围绕 LangGraph Agent 架构的核心技术选型与落地要点，是面试/汇报场景下的技术深度参考。

**更新**: 2026-05-04  
**技术栈**: LangGraph 1.x + LangChain + FastAPI + Ollama (qwen2.5:7b)

---

## 一、总体架构：Supervisor-Worker 多智能体模式

### 1.1 为什么选 Supervisor-Worker 而不是 Chain 或独立 Tool-Calling Agent？

| 对比维度 | Linear Chain | Tool-Calling Agent | Supervisor-Worker（本项目） |
|----------|-------------|-------------------|---------------------------|
| 路由决策 | 固定的 DAG | LLM 自主选择工具 | **LLM 驱动的中心化调度** |
| 并行执行 | 不支持 | 不支持 | **Send() 扇出** |
| 循环/重试 | 需手动回边 | ReAct 循环 | **Supervisor 统一控制重试路由** |
| 可观测性 | 弱 | 中 | **强（每步有决策 reason）** |
| 适合场景 | 简单 ETL | 单 Agent 多工具 | **多 Worker 协作 + 条件分支** |

Supervisor-Worker 模式是 LangGraph 的 **"Hello World++"**——比简单的 Chain 复杂，比完全自主 Agent 可控，是展示 LangGraph 核心能力的理想模式。

### 1.2 架构图

```
                    ┌──────────────┐
                    │  Supervisor  │  LLM 驱动的决策中心
                    │  (ChatOllama) │  ── 分析 state → 输出 RouterDecision
                    └──────┬───────┘
                           │ conditional edge (route_supervisor)
         ┌────────┬────────┼──────────┬──────────┬──────────┐
         ▼        ▼        ▼          ▼          ▼          ▼
    ┌────────┐┌──────────┐┌──────┐┌──────────┐┌──────────┐
    │  RAG   ││ Generate ││ Eval ││ Approval ││ Identity │
    │ Worker ││  Worker  ││Worker││  Worker  ││  Worker  │
    └───┬────┘└────┬─────┘└──┬───┘└────┬─────┘└────┬─────┘
        │          │         │         │           │
        └──────────┴─────────┴─────────┴───────────┘
                           │ Command(goto="supervisor")
                           ▼
                    ┌──────────────┐
                    │  Supervisor  │  ← 循环回到决策中心
                    └──────┬───────┘
                           │
              HITL 审批中断 (full 模式):
              Approval Worker → interrupt()
                  │
          ┌───────┴───────┐
          ▼               ▼
       Approve          Reject
       → Identity       → Generate (重生成)
```

**核心机制**:
- 每个 Worker 执行完毕后通过 `Command(goto="supervisor")` 回到调度中心
- Supervisor 重新评估整个 state，决定下一步
- 不是固定的 A→B→C 流水线，而是**动态规划**

---

## 二、关键技术落地点

### 2.1 结构化输出：RouterDecision

**问题**: Supervisor 需要输出确定性的路由指令，但 LLM 本质上是文本生成器。

**方案**: 使用 LangChain 的 `with_structured_output()` + Pydantic 模型：

```python
class RouterDecision(BaseModel):
    next: Literal["rag", "generate", "eval", "approval", "identity", "FINISH"]
    reason: str

structured_llm = llm.with_structured_output(RouterDecision, method="json_mode")
decision: RouterDecision = await structured_llm.ainvoke(messages)
```

**落地要点**:
- `method="json_mode"` 强制 Ollama 输出合法 JSON，避免解析失败
- 如果结构化输出失败，有 deterministic fallback（`_fallback_route()`），保证系统不中断
- `reason` 字段被提取到 SSE 事件中，前端实时展示 Supervisor 决策原因

### 2.2 并行扇出：Send() Fan-Out

**问题**: full 模式下，eval（质量评估）和 identity（身份校验）互不依赖，串行执行浪费时间。

**方案**: LangGraph 的 `Send()` API 支持从 conditional edge 返回多个 `Send` 对象：

```python
def route_supervisor(state) -> str | list[Send]:
    if next_worker == "__parallel__":
        return [
            Send("eval", _make_send_state(state, "eval")),
            Send("identity", _make_send_state(state, "identity")),
        ]
    return next_worker
```

**落地要点**:
- `Send()` 只能从 **conditional edge** 返回，不能从 node 内部返回——这是 LangGraph 的设计约束
- 两种返回类型（`str | list[Send]`）共存于同一个 routing function
- Parallel dispatch 后，两个 Worker 各自执行完毕回到 Supervisor → Supervisor 合并状态继续决策

### 2.3 子图嵌套：Generate Subgraph

**问题**: `generate_worker` 内部逻辑复杂（prepare_prompt → call_llm → parse_result），作为单一节点不利于测试和复用。

**方案**: 将 generate 内部流程封装为独立的 `StateGraph`：

```python
# generate_subgraph.py
subgraph = StateGraph(GenerateSubState)
subgraph.add_node("prepare_prompt", prepare_prompt_node)
subgraph.add_node("call_llm", call_llm_node)
subgraph.add_node("parse_result", parse_result_node)
subgraph.add_edge(START, "prepare_prompt")
subgraph.add_edge("prepare_prompt", "call_llm")
subgraph.add_edge("call_llm", "parse_result")
subgraph.add_edge("parse_result", END)

# workers.py — 父图中调用
subgraph = build_generate_subgraph()
result = await subgraph.ainvoke(sub_state)
```

**落地要点**:
- 子图有自己的独立 State，与父图 State 隔离
- 子图节点在 `astream(stream_mode=["updates","custom"])` 中有独立的 namespace，可实现细粒度 SSE 追踪
- 子图可独立测试（`test_generate_subgraph.py`），不需启动完整 Supervisor 流程

### 2.4 流式思考链：SSE Thought Events (v1 / legacy)

> **注意**: 以下描述的是项目最初基于 `astream_events` v1 API 的实现。当前已升级至 §2.4.1 的 Custom Streaming 方案（`astream(stream_mode=["updates","custom"])`），保留此节作为技术演进记录。

**问题**: 本地的 qwen2.5:7b 生成慢（单条 2-5s），用户如果不看到进度会认为系统卡死。

**方案 (legacy)**: 利用 LangGraph 的 `astream_events` v1 API，将 Supervisor 决策和 LLM 活动转为 SSE 事件推送到前端：

| SSE Event | 触发时机 | 前端展示 |
|-----------|---------|---------|
| `thought` (node_start) | Worker 开始执行 | `💭 Supervisor 分析当前状态，决定下一步` |
| `thought` (llm_start) | LLM 开始推理 | `🤖 Supervisor主控 LLM 开始推理...` |
| `thought` (llm_end) | LLM 推理完成 | `🤖 Supervisor主控 LLM 推理完成` |
| `thought_decision` | Supervisor 输出路由 | `🧠 [Supervisor] → generate: 质量未达标，重新生成` |
| `thought_token` | LLM token 流 | （节流后每 10 token 推一次） |

**落地要点**:
- `on_chain_end` 为 Supervisor 时，output 是 `RouterDecision` **对象**而非 dict，需特殊处理
- 各 Worker 的 `on_chain_end` 只有 partial state update，不能依赖它获取完整 `quality_score`
- 前端用 Pinia store 的 `thoughts[]` 数组 + `thoughtSeq` 自增 ID 渲染滚动日志

#### 2.4.1 Custom Streaming 升级：节点内细粒度进度

**问题**: 上述 `astream_events` 只能在节点边界报告进度。对于 30-60s 的 LLM 调用，用户看到长时间空白等待，且无法感知单条记录解析进度。

**方案**: 将 `astream_events` 升级为 `astream(stream_mode=["updates", "custom"])`，搭配 `get_stream_writer()` 在节点内部推送进度。

```python
# routes.py — 切换流模式
async for (mode, data) in graph.astream(
    initial_state, config=graph_config,
    stream_mode=["updates", "custom"],
):
    if mode == "custom":
        # data = writer() 推送的字典
        handle_custom_event(data)
    elif mode == "updates":
        node_name, state_update = data  # (str, dict)
        # 等同于 on_chain_end

# generate_subgraph.py — 节点内推送
from langgraph.config import get_stream_writer

async def parse_result_node(state):
    writer = get_stream_writer()
    for i, item in enumerate(result[:count]):
        record = TrafficRecord(...)
        records.append(record)
        if (i + 1) % 5 == 0:
            writer({"type": "generate_progress", "phase": "parse",
                    "parsed": i + 1, "total": count,
                    "message": f"已解析 {i+1}/{count} 条记录..."})
```

**新增 SSE 事件**: `generate_progress` — 四阶段子进度：

| phase | 触发 | 前端展示 |
|-------|------|---------|
| `prepare` | 提示词构建完成 | `正在构建提示词 (行业=finance, 50条)` |
| `llm_call` | 开始调用 LLM | `正在调用 LLM 生成流量数据 (超时=300s)...` |
| `llm_done` | LLM 响应返回 | `LLM 响应已收到 (12543 字符)，开始解析...` |
| `parse` | 每 5 条记录 | `已解析 25/50 条记录...` |

**落地要点**:
- `get_stream_writer()` 仅在 `stream_mode="custom"` 时可用；非流式调用（sync invoke）中返回 `None`，用 `try/except RuntimeError` 兜底
- 切换 `astream` 后丢失 `on_chain_start` / `on_chat_model_*` 事件 → 改为在各节点入口通过 `writer()` 手动推送 `stage_start` / `thought` 事件
- `("updates", (node, state_update))` 元组解包替代 `on_chain_end`，Supervisor 决策从 `state_update["messages"]` 提取

### 2.5 检查点持久化：AsyncSqliteSaver

**问题**: 服务重启后所有进行中的任务丢失，也无法回溯历史执行步骤。

**方案**: 使用 LangGraph 内置的 `AsyncSqliteSaver`：

```python
conn = aiosqlite.connect(str(checkpoint_path))
checkpointer = AsyncSqliteSaver(conn)
graph = builder.compile(checkpointer=checkpointer)
```

**落地要点**:
- 每个 `thread_id` 维护独立的检查点链
- 每次 `graph.ainvoke(state, config)` 自动保存检查点
- `graph.aget_state(config)` 可读取任意步骤的历史状态
- 当前检查点文件 `data/checkpoints.db`，约 5-50MB/会话

### 2.6 降级容错：Fallback Routing

**问题**: LLM 结构化输出可能因模型抖动而失败。

**方案**: 双重降级机制：

```python
try:
    decision = await structured_llm.ainvoke(messages)
except Exception:
    decision = _fallback_route(state)  # 纯 Python 规则引擎

def _fallback_route(state) -> RouterDecision:
    # 不需要 LLM，纯业务逻辑判断
    if retrieved_count == 0:
        return RouterDecision(next="rag", reason="尚未检索行业案例")
    if generated_count == 0:
        return RouterDecision(next="generate", reason="案例就绪，开始生成流量")
    # ... 7 条确定性规则
```

**落地要点**:
- 正常路径：LLM 结构化输出（灵活、可解释）
- 降级路径：纯 Python if-else（100% 可靠、零延迟）
- 保证了系统的 **可用性** 优先于 **智能性**

### 2.7 检查点回放：State History + Fork Replay

**问题**: 已完成的任务无法在不重新配置的情况下换个 prompt 重试；调试时也看不到每个节点的中间状态。

**方案**: 利用 LangGraph `AsyncSqliteSaver` 的 `aget_state_history()` API 遍历检查点历史，提取目标节点状态后 fork 为新会话重放。

```python
# graph_runner.py — replay_from_checkpoint()

async def replay_from_checkpoint(
    original_session_id: str, from_node: str, hint_override: str | None = None,
) -> dict:
    graph = get_traffic_graph()
    original_config = {"configurable": {"thread_id": f"traffic_{original_session_id}"}}

    # Step 1: 遍历检查点历史，找到 from_node 完成后的状态快照
    target_state = None
    async for snapshot in graph.aget_state_history(original_config):
        if snapshot.metadata.get("source") == from_node:
            target_state = snapshot.values  # StateSnapshot.values 是完整 GraphState
            break

    # Step 2: 从快照中提取所需字段
    industry = target_state["industry"]
    scenario = target_state["scenario"]
    retrieved_cases = list(target_state["retrieved_cases"])

    # Step 3: 注入可选的 hint override
    if hint_override:
        retrieved_cases.append({"type": "llm_hint", "content": hint_override})

    # Step 4: 重置质量/重试字段，创建全新 session + thread_id
    new_state = {
        "session_id": uuid.uuid4().hex[:12],
        "industry": industry, "scenario": scenario,
        "retries": 0, "quality_score": QualityScore(total_score=0, passed=False),
        "retrieved_cases": retrieved_cases, "messages": [HumanMessage(...)],
        # ... 其他字段
    }
    new_config = build_graph_config(session_id=new_state["session_id"], payload=...)

    # Step 5: Fork 重放 — 新 thread_id 独立运行，不污染原检查点
    return await graph.ainvoke(new_state, config=new_config)
```

**落地要点**:
- `aget_state_history(config)` 返回最近→最远的快照流，每个 `StateSnapshot` 包含 `values`（完整状态）和 `metadata`（step / source / timestamp）
- **Fork 而非 Resume**：不使用 LangGraph 原生 `ainvoke(None, config_with_checkpoint_id)`，而是提取状态后新建 `thread_id` 运行——每次重放都是独立会话，多次重放互不干扰
- `from_node` 参数定义重放起点：`"rag"` 表示从 RAG 完成后重放（重新生成），`"generate"` 表示从生成完成后重放（重新评估）
- 前端在已完成会话的详情卡片中提供"重放"按钮和内联面板（选择节点 + 可选自定义提示词）
- API 端点：`GET /api/v1/traffic/checkpoints/{session_id}` 列出检查点、`POST /api/v1/traffic/replay` 执行重放

---

## 三、可观测性体系

### 3.1 LangSmith @traceable 装饰器

```python
@traceable(name="evaluate_quality", process_outputs=lambda r: {
    "total_score": r.total_score, "passed": r.passed,
    "format": r.format_score, "business": r.business_score, "diversity": r.diversity_score,
})
def evaluate_quality(records, industry) -> QualityScore: ...
```

- 条件导入：`LANGCHAIN_TRACING_V2 != "true"` 时 `@traceable` 是 no-op
- `process_outputs` 摘要化大对象（避免全量 traffic records 入 trace）
- 与 `session_id` / `thread_id` 关联，可串联追踪整条链路

### 3.2 SSE 阶段进度

- `stage_start` / `stage_complete` 事件：五阶段进度条 (RAG/生成/评估/审批/身份校验)
- `progress` 事件：百分比进度
- 所有事件带 `session_id`，前端可同时追踪多个并发会话

---

## 四、当前限制与后续提升方向

### 已识别限制

| 限制 | 原因 | 影响 |
|------|------|------|
| 取消不立即中断 LLM | LLM 调用期间无法检查取消标记 | 取消延迟 = LLM 剩余调用时长 |
| RAG 为静态示例 | 读文件而非向量检索 | 无法利用成功案例自我进化 |

### 后续提升方向（详见 ROADMAP.md 第六节）

1. **真 RAG 向量检索 (ChromaDB)** — 静态示例 → 动态知识库
2. **Docker 容器化部署** — 解决环境依赖问题
3. **API 鉴权** — 引入 JWT 或 API Key 机制

---

## 五、关键文件索引

| 文件 | 职责 |
|------|------|
| `backend/app/graph/workflow.py` | Supervisor-Worker 图编译 + Send() 并行路由 |
| `backend/app/graph/supervisor.py` | Supervisor 决策节点 + fallback 路由 |
| `backend/app/graph/workers.py` | 5 个 Worker 实现（RAG / Generate / Eval / Approval / Identity） |
| `backend/app/graph/generate_subgraph.py` | Generate 子图（prompt→LLM→parse） |
| `backend/app/graph/state.py` | `GraphState` TypedDict 定义 |
| `backend/app/api/routes.py` | SSE 流式端点 + thought 事件发射 |
| `backend/app/services/generator.py` | LLM 调用 + 质量评分 + @traceable |
| `backend/app/services/graph_runner.py` | 图执行入口 + 检查点回放 (`replay_from_checkpoint`) |
| `frontend/src/stores/trafficStore.ts` | 前端 Pinia store（thoughts[] + SSE 回调） |
| `frontend/src/components/GeneratePanel.vue` | 生成面板 UI（含思考链展示） |
| `frontend/src/components/HistoryPanel.vue` | 历史面板 UI（含重放按钮） |
