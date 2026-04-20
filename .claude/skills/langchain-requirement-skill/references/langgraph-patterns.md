# LangGraph 架构模式参考

## 核心概念

### StateGraph
LangGraph 的核心数据结构，用于定义有状态的多步骤工作流。

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    messages: list
    current_agent: str
    task_result: dict

def create_agent_graph():
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("evaluator", evaluator_node)

    # 设置入口点
    workflow.set_entry_point("planner")

    # 添加边
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "evaluator")
    workflow.add_edge("evaluator", END)

    return workflow.compile()
```

### 预建组件

| 组件 | 用途 |
|------|------|
| create_react_agent | 构建 ReAct 推理 Agent |
| create_tool_calling_agent | 构建工具调用 Agent |
| create_openai_functions_agent | OpenAI 函数调用 Agent |

## Agent 模式

### 1. Tool-calling Agent
适用于有明确工具集的任务。

```python
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.tools import tool

@tool
def search_milvus(query: str):
    """Search Milvus vector store"""
    pass

tools = [search_milvus]
llm = ChatOpenAI(model="gpt-4")
agent = create_tool_calling_agent(llm, tools, prompt)
```

### 2. Multi-Agent 协作

#### Sequential 模式
```python
from langgraph.graph import StateGraph, START, END

# 定义状态
class MultiAgentState(TypedDict):
    task: str
    result_1: str
    result_2: str

# 创建工作流
graph = StateGraph(MultiAgentState)
graph.add_node("agent1", agent1_node)
graph.add_node("agent2", agent2_node)
graph.add_edge(START, "agent1")
graph.add_edge("agent1", "agent2")
graph.add_edge("agent2", END)
```

#### Supervisor 模式
```python
# Supervisor 决定下一步调用哪个 Agent
def supervisor_node(state: MultiAgentState) -> str:
    """决定下一个执行的 Agent"""
    if needs_planning(state):
        return "planner"
    elif needs_execution(state):
        return "executor"
    else:
        return END
```

### 3. Plan-and-Execute
分离规划与执行，提高复杂任务处理能力。

```python
# 1. 规划阶段
planner = create_react_agent(model, planning_tools)
plan = planner.invoke({"messages": [user_input]})

# 2. 执行阶段
executor = create_react_agent(model, action_tools)
for step in plan.steps:
    executor.invoke({"task": step})
```

## 状态管理

### 短期记忆
```python
from langchain.memory import ConversationBufferMemory

memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)
```

### 长期记忆 (RAG)
```python
from langchain_core.vectorstores import VectorStore
from langchain_core.retrievers import Retriever

# Milvus Retriever
vectorstore = Milvus(embedding_function=embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# 用于记忆检索
memory_store = VectorStoreRetrieverMemory(
    retriever=retriever
)
```

## 工具集成

### BaseTool 自定义
```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel

class TrafficInput(BaseModel):
    vehicle_id: str
    location: str

class TrafficIdentityTool(BaseTool):
    name = "traffic_identity_lookup"
    description = "查询车辆身份信息"
    args_schema = TrafficInput

    def _run(self, vehicle_id: str, location: str):
        # 实现逻辑
        return result
```

## 错误处理

### 重试机制
```python
from langgraph.prebuilt import ToolNode
from tenacity import retry, stop_after_attempt

@retry(stop=stop_after_attempt(3))
def robust_tool_call(tool, input_data):
    return tool.invoke(input_data)
```

### 条件边处理
```python
def should_continue(state):
    if state.get("max_iterations", 0) > 10:
        return "end"
    elif state.get("error_count", 0) > 3:
        return "fallback"
    return "continue"

workflow.add_conditional_edges(
    "executor",
    should_continue,
    {
        "end": END,
        "fallback": "fallback_node",
        "continue": "planner"
    }
)
```

## 评估策略

### 内置评估工具
```python
from langchain.evaluation import load_evaluator

evaluator = load_evaluator("qa")
result = evaluator.evaluate_strings(
    prediction=agent_output,
    reference=expected_answer,
    input=user_question
)
```

### 自定义 EvalTool
```python
class EvalTool(BaseTool):
    name = "evaluate_result"
    description = "评估 Agent 输出质量"

    def _run(self, prediction: str, criteria: str):
        # 实现评估逻辑
        return {"score": score, "feedback": feedback}
```
