# Traffic Agent — Agent 核心技术落地

> 本文档介绍 Traffic Agent 项目中围绕 LangGraph Agent 架构的核心技术选型与落地要点，是面试/汇报场景下的技术深度参考。

**更新**: 2026-04-29  
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
              ┌────────────┼──────────────┬─────────────┐
              ▼            ▼              ▼             ▼
         ┌────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
         │  RAG   │  │ Generate │  │   Eval   │  │ Identity │
         │ Worker │  │  Worker  │  │  Worker  │  │  Worker  │
         └───┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
             │            │             │             │
             └────────────┴─────────────┴─────────────┘
                           │ Command(goto="supervisor")
                           ▼
                    ┌──────────────┐
                    │  Supervisor  │  ← 循环回到决策中心
                    └──────────────┘
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
    next: Literal["rag", "generate", "eval", "identity", "FINISH"]
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
- 子图节点在 `astream_events` 中有独立的 namespace，可实现细粒度 SSE 追踪
- 子图可独立测试（`test_generate_subgraph.py`），不需启动完整 Supervisor 流程

### 2.4 流式思考链：SSE Thought Events

**问题**: 本地的 qwen2.5:7b 生成慢（单条 2-5s），用户如果不看到进度会认为系统卡死。

**方案**: 利用 LangGraph 的 `astream_events` v1 API，将 Supervisor 决策和 LLM 活动转为 SSE 事件推送到前端：

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

- `stage_start` / `stage_complete` 事件：四阶段进度条
- `progress` 事件：百分比进度
- 所有事件带 `session_id`，前端可同时追踪多个并发会话

---

## 四、当前限制与后续提升方向

### 已识别限制

| 限制 | 原因 | 影响 |
|------|------|------|
| 取消不立即中断 LLM | LLM 调用期间无法检查取消标记 | 取消延迟 = LLM 剩余调用时长 |
| 质量重试无硬上限 | Supervisor 仅建议重试，无全局计数 | qwen2.5:7b 可能陷入重试循环 |
| RAG 为静态示例 | 读文件而非向量检索 | 无法利用成功案例自我进化 |

### 后续提升方向（详见 ROADMAP.md 第六节）

1. **Checkpoint Replay / Time Travel** — 检查点回放，调试 + 重试能力
2. **真 RAG 向量检索 (ChromaDB)** — 静态示例 → 动态知识库
3. **质量重试硬上限 + 降级策略** — 修复重试循环
4. **Prompt 自优化反馈闭环** — 利用评估结果反向改进 prompt

---

## 五、关键文件索引

| 文件 | 职责 |
|------|------|
| `backend/app/graph/workflow.py` | Supervisor-Worker 图编译 + Send() 并行路由 |
| `backend/app/graph/supervisor.py` | Supervisor 决策节点 + fallback 路由 |
| `backend/app/graph/workers.py` | 4 个 Worker 实现（RAG / Generate / Eval / Identity） |
| `backend/app/graph/generate_subgraph.py` | Generate 子图（prompt→LLM→parse） |
| `backend/app/graph/state.py` | `GraphState` TypedDict 定义 |
| `backend/app/api/routes.py` | SSE 流式端点 + thought 事件发射 |
| `backend/app/services/generator.py` | LLM 调用 + 质量评分 + @traceable |
| `frontend/src/stores/trafficStore.ts` | 前端 Pinia store（thoughts[] + SSE 回调） |
| `frontend/src/components/GeneratePanel.vue` | 生成面板 UI（含思考链展示） |
