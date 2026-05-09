import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    BatchGenerateRequest,
    BatchStatusResponse,
    BatchTaskStatus,
    SessionStatus,
    TrafficGenerateRequest,
)
from app.services.session_service import (
    add_batch_task,
    create_batch,
    get_batch_tasks,
)
from app.api.deps import _run_single_task

router = APIRouter()


@router.post("/batch")
async def start_batch(payload: BatchGenerateRequest) -> dict:
    batch_id = uuid.uuid4().hex[:8]
    await create_batch(batch_id)

    session_ids: list[str] = [uuid.uuid4().hex[:12] for _ in payload.tasks]

    for idx, task in enumerate(payload.tasks):
        await add_batch_task(
            batch_id=batch_id,
            task_index=idx,
            session_id=session_ids[idx],
            industry=task.industry,
            stage=task.stage.value,
            count=task.count,
        )

    for idx, task in enumerate(payload.tasks):
        asyncio.create_task(
            _run_single_task(
                batch_id=batch_id,
                task_index=idx,
                session_id=session_ids[idx],
                industry=task.industry,
                stage=task.stage.value,
                count=task.count,
            )
        )

    return {"success": True, "batch_id": batch_id}


@router.get("/batch/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str) -> BatchStatusResponse:
    tasks_rows = await get_batch_tasks(batch_id)
    if not tasks_rows:
        raise HTTPException(status_code=404, detail="批次不存在")

    tasks = []
    all_done = True
    for row in tasks_rows:
        status = SessionStatus(row["status"])
        if status not in (SessionStatus.completed, SessionStatus.failed, SessionStatus.cancelled):
            all_done = False
        progress = 100 if status == SessionStatus.completed else (50 if status == SessionStatus.processing else 0)

        from app.models.schemas import Stage as StageEnum

        tasks.append(
            BatchTaskStatus(
                index=row["task_index"],
                industry=row["industry"],
                stage=StageEnum(row["stage"]),
                count=row["count"],
                session_id=row["session_id"],
                status=status,
                progress=progress,
                error_message=row.get("error_message"),
            )
        )

    return BatchStatusResponse(batch_id=batch_id, tasks=tasks, finished=all_done)


@router.post("/batch/{batch_id}/retry-failed")
async def retry_failed_batch_tasks(batch_id: str) -> dict:
    """Retry all failed tasks in a batch."""
    tasks_rows = await get_batch_tasks(batch_id)
    if not tasks_rows:
        raise HTTPException(status_code=404, detail="批次不存在")

    failed_tasks = [row for row in tasks_rows if row["status"] == "failed"]
    if not failed_tasks:
        return {"success": True, "batch_id": batch_id, "retried": 0, "message": "没有失败的任务"}

    for row in failed_tasks:
        asyncio.create_task(
            _run_single_task(
                batch_id=batch_id,
                task_index=row["task_index"],
                session_id=row["session_id"],
                industry=row["industry"],
                stage=row["stage"],
                count=row["count"],
            )
        )

    return {
        "success": True,
        "batch_id": batch_id,
        "retried": len(failed_tasks),
        "message": f"已重试 {len(failed_tasks)} 个失败任务",
    }
