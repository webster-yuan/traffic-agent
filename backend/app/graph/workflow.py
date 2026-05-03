"""Supervisor-Worker StateGraph for Traffic Agent.

Builds a multi-agent orchestration graph where:
- ``supervisor`` (LLM-driven) decides which worker to invoke next
- ``rag`` / ``generate`` / ``eval`` / ``identity`` workers execute tasks
- All workers return to supervisor via ``Command(goto="supervisor")``
"""

from __future__ import annotations

import aiosqlite
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.graph.state import GraphState
from app.graph.supervisor import supervisor_node
from app.graph.workers import (
    eval_worker,
    generate_worker,
    identity_worker,
    rag_worker,
)

_WORKERS = ("rag", "generate", "eval", "identity")


def _build_graph() -> StateGraph:
    """Construct the Supervisor-Worker agent graph.

    Layout::

        START → supervisor ──→ rag ──→ supervisor
                         ├──→ generate ──→ supervisor
                         ├──→ eval ──→ supervisor
                         ├──→ identity ──→ supervisor
                         └──→ END
    """
    builder = StateGraph(GraphState)

    # -- nodes ---------------------------------------------------------------
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("rag", rag_worker)
    builder.add_node("generate", generate_worker)
    builder.add_node("eval", eval_worker)
    builder.add_node("identity", identity_worker)

    # -- edges ---------------------------------------------------------------
    builder.add_edge(START, "supervisor")

    # Workers always return to supervisor via Command(goto="supervisor").
    # Static edges serve as fallback documentation.
    for name in _WORKERS:
        builder.add_edge(name, "supervisor")

    return builder


@lru_cache(maxsize=1)
def get_traffic_graph():
    """Return a compiled graph with SQLite checkpoint persistence (lazy-init)."""
    checkpoint_path = Path(settings.checkpoint_db_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    builder = _build_graph()
    conn = aiosqlite.connect(str(checkpoint_path))
    checkpointer = AsyncSqliteSaver(conn)
    return builder.compile(checkpointer=checkpointer)


# Module-level compiled graph for langgraph.json dev-server compatibility.
graph = _build_graph().compile()
