from typing import Any

from app.models.schemas import TrafficGenerateRequest


def build_graph_config(
    session_id: str,
    payload: TrafficGenerateRequest,
    source: str = "frontend",
) -> dict[str, Any]:
    stage = payload.stage.value
    return {
        "configurable": {"thread_id": f"traffic_{session_id}"},
        "run_name": "traffic_generation",
        "tags": ["traffic-agent", source, payload.industry, stage],
        "metadata": {
            "session_id": session_id,
            "industry": payload.industry,
            "stage": stage,
            "count": payload.count,
            "source": source,
        },
    }
