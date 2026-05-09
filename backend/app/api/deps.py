import asyncio
import logging

from app.models.schemas import SessionStatus, TrafficGenerateRequest
from app.services.generator import write_csv, write_traffic_json, write_traffic_parquet
from app.services.graph_runner import run_generation_graph_async as run_graph
from app.services.tracing_config import build_graph_config
from app.services.session_service import (
    complete_session,
    create_session,
    fail_session,
    update_batch_task_status,
)

logger = logging.getLogger(__name__)

_semaphore = asyncio.Semaphore(3)


async def _acquire() -> None:
    await _semaphore.acquire()


def _release() -> None:
    _semaphore.release()


async def _run_single_task(
    batch_id: str,
    task_index: int,
    session_id: str,
    industry: str,
    stage: str,
    count: int,
) -> None:
    """Run a single generation task as part of a batch."""
    await _acquire()
    try:
        from app.models.schemas import Stage

        payload = TrafficGenerateRequest(
            industry=industry,
            count=count,
            stage=Stage(stage),
        )
        graph_config = build_graph_config(session_id=session_id, payload=payload)
        await create_session(
            session_id=session_id,
            industry=industry,
            scenario="",
            stage=Stage(stage),
            status=SessionStatus.processing,
            requested_count=count,
            record_count=0,
            quality_score=None,
            file_path=None,
            trace_thread_id=graph_config["configurable"]["thread_id"],
            trace_metadata=graph_config["metadata"],
        )
        await update_batch_task_status(batch_id, task_index, "processing")

        graph_result = await run_graph(session_id=session_id, payload=payload)
        scenario = graph_result["scenario"]
        quality = graph_result["quality_score"]
        records = graph_result["generated_records"]
        file_path = write_csv(session_id, records, industry)
        write_traffic_json(
            session_id, records, industry,
            scenario=scenario, quality=quality, stage=Stage(stage),
        )
        write_traffic_parquet(session_id, records, industry)
        await complete_session(
            session_id=session_id,
            scenario=scenario,
            record_count=len(records),
            file_path=file_path,
            quality=quality,
        )
        await update_batch_task_status(batch_id, task_index, "completed")
    except Exception as e:
        await fail_session(session_id, str(e))
        await update_batch_task_status(batch_id, task_index, "failed", str(e))
    finally:
        _release()
