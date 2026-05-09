import logging
import time

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    CheckpointItem,
    CheckpointListResponse,
    SessionStatus,
    TrafficGenerateRequest,
    TrafficGenerateResponse,
    TrafficReplayRequest,
)
from app.graph.workflow import get_traffic_graph
from app.services.generator import write_csv, write_traffic_json, write_traffic_parquet
from app.services.graph_runner import replay_from_checkpoint
from app.services.tracing_config import build_graph_config
from app.services.session_service import (
    complete_session,
    create_session,
    fail_session,
)
from app.api.deps import _acquire, _release

router = APIRouter()


@router.get("/checkpoints/{session_id}", response_model=CheckpointListResponse)
async def list_checkpoints(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
) -> CheckpointListResponse:
    """List checkpoints for a completed session with cursor pagination."""
    graph = get_traffic_graph()
    thread_id = f"traffic_{session_id}"
    config: dict = {"configurable": {"thread_id": thread_id}}

    items: list[CheckpointItem] = []
    kwargs: dict = {"limit": limit}
    if before:
        kwargs["before"] = {"configurable": {"thread_id": thread_id, "checkpoint_id": before}}
    async for snapshot in graph.aget_state_history(config, **kwargs):
        metadata = snapshot.metadata or {}
        cid = snapshot.config.get("configurable", {}).get("checkpoint_id", "")
        items.append(
            CheckpointItem(
                checkpoint_id=str(cid),
                step=metadata.get("step", 0),
                node_name=metadata.get("source", "unknown"),
                timestamp=str(metadata.get("timestamp", "")),
            )
        )

    return CheckpointListResponse(session_id=session_id, checkpoints=items)


@router.post("/replay", response_model=TrafficGenerateResponse)
async def replay_traffic(payload: TrafficReplayRequest) -> TrafficGenerateResponse:
    """Replay a session from a specific checkpoint node."""
    await _acquire()
    start_at = time.perf_counter()
    new_session_id = ""
    try:
        graph_result = await replay_from_checkpoint(
            original_session_id=payload.session_id,
            from_node=payload.from_node,
            hint_override=payload.hint_override,
        )
        new_session_id = graph_result["session_id"]
        scenario = graph_result["scenario"]
        quality = graph_result["quality_score"]
        records = graph_result["generated_records"]

        dummy_payload = TrafficGenerateRequest(
            industry=graph_result["industry"],
            count=graph_result["count"],
            stage=graph_result["stage"],
        )
        graph_config = build_graph_config(
            session_id=new_session_id, payload=dummy_payload,
        )
        await create_session(
            session_id=new_session_id,
            industry=graph_result["industry"],
            scenario=scenario,
            stage=graph_result["stage"],
            status=SessionStatus.processing,
            requested_count=graph_result["count"],
            record_count=0,
            quality_score=None,
            file_path=None,
            trace_thread_id=graph_config["configurable"]["thread_id"],
            trace_metadata=graph_config["metadata"],
        )

        file_path = write_csv(new_session_id, records, graph_result["industry"])
        write_traffic_json(
            new_session_id, records, graph_result["industry"],
            scenario=scenario, quality=quality, stage=graph_result["stage"],
        )
        write_traffic_parquet(new_session_id, records, graph_result["industry"])
        await complete_session(
            session_id=new_session_id,
            scenario=scenario,
            record_count=len(records),
            file_path=file_path,
            quality=quality,
        )

        return TrafficGenerateResponse(
            success=True,
            session_id=new_session_id,
            total_count=len(records),
            quality_score=quality,
            generated_data=records,
            processing_time_ms=int((time.perf_counter() - start_at) * 1000),
        )
    except Exception as e:
        if new_session_id:
            await fail_session(new_session_id, str(e))
        raise
    finally:
        _release()
