"""Graph execution helpers for Supervisor-Worker agent graph."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.graph.workflow import get_traffic_graph
from app.models.schemas import QualityScore, TrafficGenerateRequest
from app.services.tracing_config import build_graph_config


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
