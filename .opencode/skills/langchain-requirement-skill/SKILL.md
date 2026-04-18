---
name: langchain-requirement
description: |
  理解和分析基于 LangChain/LangGraph 的 AI Agent 项目需求，并生成结构化分析和代码骨架。当用户分享关于 LangChain、LangGraph、Agent、RAG、FastAPI 的项目需求文档、PDF、技术方案或架构描述时，立即触发此 skill。特别适用于：
  - 分析 Agent 架构设计（StateGraph、SequentialChain、Multi-Agent）
  - 识别多组件协作模式和工具链
  - 提取技术栈并推荐选型
  - 生成 StateGraph 代码骨架
  - 识别需求模糊点并生成追问模板
  如果用户说"帮我理解需求"、"分析这个技术方案"、"这个 LangChain 项目"、"我想做 RAG Agent"或类似表述，触发此 skill。
---

# LangChain/LangGraph 需求分析 Skill

## 工作流程

```
输入需求 → 技术栈识别 → 架构分析 → 模糊点识别 → 结构化输出 → (可选)代码骨架
```

## 1. 技术栈识别

逐项检查需求中是否提到：

| 类别 | 常见关键词 |
|------|------------|
| LLM 框架 | LangChain, LangGraph, LlamaIndex |
| 编排模式 | Chain, Agent, StateGraph, SequentialChain, ConversationChain |
| RAG 组件 | Milvus, Chroma, Pinecone, FAISS, Weaviate, Qdrant |
| 向量化 | OpenAI Embeddings, BGE, Jina, Sentence Transformers |
| 后端框架 | FastAPI, Flask, Django |
| Agent 类型 | Tool-calling, ReAct, Plan-and-Execute, Supervisor |

**快速提取**：直接识别并列出所有识别的组件。

## 2. Agent 架构分析

### 2.1 检查五大核心能力

对于每个需求，检查是否覆盖：

| 能力 | 关键问题 |
|------|----------|
| 目标导向 | Agent 任务目标是什么？成功/失败如何定义？ |
| 工具使用 | 哪些工具？工具与 LLM 如何集成？ |
| 决策制定 | 单 Agent 还是多 Agent？编排模式？ |
| 状态管理 | 短期记忆？长期记忆？如何持久化？ |
| 错误处理 | 失败时的回退策略？ |

### 2.2 LangGraph 特有分析

若提到 StateGraph，识别：

- **State 结构**：状态包含哪些字段？
- **Nodes**：有哪些处理节点？
- **Edges**：节点间如何流转？
- **条件边**：条件分支逻辑？

## 3. 模糊点识别

使用此检查表：

| 检查项 | 缺失时的追问 |
|--------|--------------|
| LLM 模型 | "使用什么 LLM？GPT-4/Claude/国产模型？" |
| Embedding | "使用什么 Embedding 模型？" |
| 工具输入输出 | "工具的具体输入输出是什么？" |
| 评估标准 | "如何衡量 Agent 效果？" |
| 性能要求 | "QPS、延迟要求是多少？" |
| API 接口 | "与现有系统的接口规范？" |

## 4. 输出格式

### Part 1: 需求摘要 (1-2句)
一句话总结核心目标。

### Part 2: 技术栈清单
```
- LLM: [识别到/待确认]
- 框架: [识别到/待确认]
- 后端: [识别到/待确认]
- RAG: [识别到/待确认]
- 工具: [列出所有识别到的工具]
```

### Part 3: 架构分析
```
[文本版架构图]

Agent 能力覆盖:
- [x] 目标导向
- [ ] 工具使用 - 缺失：xxx
- ...
```

### Part 4: 待澄清问题 (用追问生成器，见下方)

### Part 5: 潜在挑战
识别 2-3 个技术难点及建议。

### Part 6: 代码骨架 (可选)
如果用户请求或适合，生成 StateGraph 基础代码。

## 5. 追问生成器

根据识别的缺失信息，自动生成追问模板：

```
## 需要您澄清的问题

### 功能边界
1. [工具名] 的输入是什么？输出是什么？是否需要调用外部 API？
2. ...

### 技术选型
1. LLM 选择？[如果缺失]
2. Embedding 模型？[如果缺失]
3. ...

### 评估标准
1. 如何定义"成功"？有哪些可量化的指标？
2. ...
```

## 6. StateGraph 代码生成模板

当需要生成代码时，使用此模板：

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

# 1. 定义 State
class AgentState(TypedDict):
    messages: list
    task: str
    context: dict
    result: str

# 2. 定义 Nodes
def [node_name]_node(state: AgentState) -> AgentState:
    """节点描述"""
    # TODO: 实现逻辑
    return {"...: "..."}

# 3. 创建 Graph
workflow = StateGraph(AgentState)

# 4. 添加节点
workflow.add_node("[node_1]", [node_1]_node)
workflow.add_node("[node_2]", [node_2]_node)

# 5. 添加边
workflow.add_edge(START, "[node_1]")
workflow.add_edge("[node_1]", "[node_2]")
workflow.add_edge("[node_2]", END)

# 6. 编译
graph = workflow.compile()
```

## 7. 工具定义代码模板

```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

class [ToolName]Input(BaseModel):
    """工具输入 schema"""
    param1: str = Field(description="参数描述")

class [ToolName]Tool(BaseTool):
    name = "[tool_name]"
    description = "[工具用途]"
    args_schema = [ToolName]Input

    def _run(self, param1: str) -> str:
        """执行逻辑"""
        # TODO: 实现
        return result
```

## 8. 快速参考

| 模式 | 适用场景 | 特点 |
|------|----------|------|
| SequentialChain | 固定顺序的多步骤任务 | 简单，线性执行 |
| Supervisor | 动态选择执行哪个 Agent | 灵活，需要路由逻辑 |
| Plan-and-Execute | 复杂任务的规划与执行分离 | 适合长任务 |
| StateGraph | 需要维护复杂状态的流程 | 最灵活，可循环 |

## 参考资料

详细代码示例见 `references/langgraph-patterns.md`。
