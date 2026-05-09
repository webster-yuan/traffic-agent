import logging
from datetime import date
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services.session_service import (
    delete_session,
    get_session_file,
    list_history,
)

router = APIRouter()


@router.get("/download/{session_id}")
async def download_traffic(
    session_id: str,
    file_format: Literal["csv", "json", "parquet"] = Query("csv", alias="format"),
) -> FileResponse:
    file_path = await get_session_file(session_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if file_format == "json":
        path = path.with_suffix(".json")
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail="JSON 文件不存在，该任务可能为旧数据或需重新生成",
            )
        return FileResponse(
            path=path,
            filename=path.name,
            media_type="application/json",
        )
    if file_format == "parquet":
        path = path.with_suffix(".parquet")
        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail="Parquet 文件不存在，该任务可能为旧数据或需重新生成",
            )
        return FileResponse(
            path=path,
            filename=path.name,
            media_type="application/vnd.apache.parquet",
        )
    return FileResponse(path=path, filename=path.name, media_type="text/csv")


@router.get("/history")
async def get_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, description="搜索关键字 (session_id/行业/场景/错误)"),
    industry: str | None = Query(default=None, description="行业过滤"),
    stage: str | None = Query(default=None, description="阶段过滤 (quick/standard/full)"),
    status: str | None = Query(default=None, description="状态过滤 (completed/failed/cancelled)"),
    date_from: date | None = Query(default=None, description="起始日期 (YYYY-MM-DD)"),
    date_to: date | None = Query(default=None, description="结束日期 (YYYY-MM-DD)"),
    min_quality: float | None = Query(default=None, ge=0, le=100, description="最低评分 (0-100)"),
) -> dict:
    total, items = await list_history(
        page, page_size,
        keyword=keyword,
        industry=industry,
        stage=stage,
        status=status,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        min_quality=min_quality,
    )
    total_pages = (total + page_size - 1) // page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": [item.model_dump() for item in items],
    }


@router.delete("/history/{session_id}")
async def remove_history(session_id: str) -> dict[str, str | bool]:
    file_path = await get_session_file(session_id)
    if file_path:
        file = Path(file_path)
        if file.exists():
            file.unlink()
    await delete_session(session_id)
    return {"success": True, "session_id": session_id, "message": "删除成功"}
