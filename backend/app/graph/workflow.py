import aiosqlite
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.graph.nodes import (
    eval_node,
    generate_node,
    identity_node,
    rag_node,
    should_retry_after_eval,
)
from app.graph.state import GraphState


@lru_cache(maxsize=1)
def get_traffic_graph():
    checkpoint_path = Path(settings.checkpoint_db_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    builder = StateGraph(GraphState)
    builder.add_node("rag", rag_node)
    builder.add_node("generate", generate_node)
    builder.add_node("eval", eval_node)
    builder.add_node("identity", identity_node)

    builder.add_edge(START, "rag")
    builder.add_edge("rag", "generate")
    builder.add_edge("generate", "eval")
    builder.add_conditional_edges(
        "eval",
        should_retry_after_eval,
        {"generate": "generate", "identity": "identity"},
    )
    builder.add_edge("identity", END)

    conn = aiosqlite.connect(str(checkpoint_path))
    checkpointer = AsyncSqliteSaver(conn)
    return builder.compile(checkpointer=checkpointer)
