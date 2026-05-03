"""Graph execution helpers for Supervisor-Worker agent graph."""

from __future__ import annotations

import uuid
import logging

from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.graph.workflow import get_traffic_graph
from app.models.schemas import QualityScore, Stage, TrafficGenerateRequest
from app.services.tracing_config import build_graph_config

logger = logging.getLogger(__name__)


def build_initial_state(session_id: str, payload: TrafficGenerateRequest) -> dict:
    """Build initial AgentState for the Supervisor-Worker graph."""
    return {
        "session_id": session_id,
        "industry": payload.industry,
        "stage": payload.stage,
        "count": payload.count,
        "scenario": "",
        "retries": 0,
        "max_retries": settings.max_retry_count,
        "retrieved_cases": [],
        "generated_records": [],
        "quality_score": QualityScore(
            format_score=0,
            business_score=0,
            diversity_score=0,
            total_score=0,
            passed=False,
        ),
        "quality_passed": False,
        "should_retry": False,
        "identity_checked": False,
        "approval_action": "",
        "approval_hint": "",
        "error_message": "",
        # Supervisor-Worker orchestration fields
        "messages": [
            HumanMessage(
                content=f"新任务: industry={payload.industry}, count={payload.count}, stage={payload.stage.value}",
                name="user",
            ),
        ],
        "next_worker": "supervisor",
    }


async def run_generation_graph(session_id: str, payload: TrafficGenerateRequest) -> dict:
    """Graph invocation — always async since graph uses AsyncSqliteSaver."""
    graph = get_traffic_graph()
    state = build_initial_state(session_id, payload)
    config = build_graph_config(session_id=session_id, payload=payload)
    result = await graph.ainvoke(state, config=config)
    return result


async def run_generation_graph_async(
    session_id: str, payload: TrafficGenerateRequest
) -> dict:
    """Async graph invocation — preferred path for batch / production use."""
    graph = get_traffic_graph()
    state = build_initial_state(session_id, payload)
    config = build_graph_config(session_id=session_id, payload=payload)
    result = await graph.ainvoke(state, config=config)
    return result


async def replay_from_checkpoint(
    original_session_id: str,
    from_node: str,
    hint_override: str | None = None,
) -> dict:
    """Replay a session from the state after *from_node* completed.

    Loads the checkpoint state produced by *from_node*, applies an optional
    hint override, and runs the graph with a fresh ``session_id`` and
    ``thread_id`` so the replay is an independent session.
    """
    graph = get_traffic_graph()

    # Build config pointing to the original session's thread
    original_thread_id = f"traffic_{original_session_id}"
    original_config: dict = {"configurable": {"thread_id": original_thread_id}}

    # Walk checkpoint history to find the snapshot after *from_node*
    target_state: dict | None = None
    async for snapshot in graph.aget_state_history(original_config):
        metadata = snapshot.metadata or {}
        source: str = metadata.get("source", "")
        if source == from_node:
            target_state = snapshot.values
            logger.info(
                "replay: found checkpoint after node=%s step=%s",
                from_node,
                metadata.get("step"),
            )
            break

    if target_state is None:
        raise ValueError(
            f"No checkpoint found after node '{from_node}' "
            f"for session {original_session_id}"
        )

    # Extract fields needed by the graph from the checkpoint state
    industry: str = target_state.get("industry", "")
    scenario: str = target_state.get("scenario", "")
    stage_raw = target_state.get("stage")
    count: int = target_state.get("count", 0)
    retrieved_cases: list = list(target_state.get("retrieved_cases", []) or [])
    generated_records: list = list(target_state.get("generated_records", []) or [])

    # Normalise stage
    if isinstance(stage_raw, Stage):
        stage = stage_raw
    elif isinstance(stage_raw, str) and stage_raw:
        stage = Stage(stage_raw)
    else:
        stage = Stage.standard

    # Reset quality / retry fields so replay re-evaluates
    quality_score = QualityScore(
        format_score=0, business_score=0, diversity_score=0,
        total_score=0, passed=False,
    )

    # Inject hint override if provided
    if hint_override:
        retrieved_cases.append({"type": "llm_hint", "content": hint_override})
        logger.info("replay: hint override injected")

    new_session_id = uuid.uuid4().hex[:12]

    new_state: dict = {
        "session_id": new_session_id,
        "industry": industry,
        "stage": stage,
        "count": count,
        "scenario": scenario,
        "retries": 0,
        "max_retries": settings.max_retry_count,
        "retrieved_cases": retrieved_cases,
        "generated_records": generated_records,
        "quality_score": quality_score,
        "quality_passed": False,
        "should_retry": False,
        "identity_checked": False,
        "approval_action": "",
        "approval_hint": "",
        "error_message": "",
        "messages": [
            HumanMessage(
                content=(
                    f"重放任务 (原session={original_session_id}): "
                    f"industry={industry}, count={count}, stage={stage.value}"
                ),
                name="user",
            ),
        ],
        "next_worker": "supervisor",
    }

    # Build a minimal TrafficGenerateRequest for build_graph_config
    dummy_payload = TrafficGenerateRequest(
        industry=industry,  # type: ignore[arg-type]
        count=count,
        stage=stage,
    )
    new_config = build_graph_config(
        session_id=new_session_id, payload=dummy_payload,
    )

    logger.info(
        "replay: starting replay session_id=%s from node=%s",
        new_session_id, from_node,
    )
    result = await graph.ainvoke(new_state, config=new_config)
    return result
