import os
from app.core.config import settings
from app.graph.workflow import get_traffic_graph
from app.models.schemas import QualityScore, TrafficGenerateRequest


def build_initial_state(session_id: str, payload: TrafficGenerateRequest) -> dict:
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
    }


def run_generation_graph(session_id: str, payload: TrafficGenerateRequest) -> dict:
    graph = get_traffic_graph()
    state = build_initial_state(session_id, payload)
    result = graph.invoke(
        state,
        config={"configurable": {"thread_id": f"traffic_{session_id}"}},
    )
    return result
