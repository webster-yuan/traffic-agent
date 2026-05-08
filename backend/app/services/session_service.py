import logging
import json
from datetime import datetime, timezone

from app.db.database import get_connection
from app.models.schemas import QualityScore, SessionStatus, SessionSummary, Stage

logger = logging.getLogger(__name__)


async def create_session(
    session_id: str,
    industry: str,
    scenario: str,
    stage: Stage,
    status: SessionStatus,
    record_count: int,
    quality_score: float | None,
    file_path: str | None,
    requested_count: int = 0,
    trace_thread_id: str | None = None,
    trace_metadata: dict | None = None,
    error_message: str | None = None,
) -> None:
    logger.info(f"创建会话: session_id={session_id}, industry={industry}, records={record_count}")
    now = datetime.now(timezone.utc).isoformat()
    conn = await get_connection()
    await conn.execute(
        """
        INSERT INTO traffic_sessions (
            id, industry, scenario, stage, status, requested_count, record_count,
            quality_score, file_path, trace_thread_id, trace_metadata, error_message,
            started_at, completed_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            industry = excluded.industry,
            scenario = excluded.scenario,
            stage = excluded.stage,
            status = excluded.status,
            requested_count = excluded.requested_count,
            record_count = excluded.record_count,
            quality_score = excluded.quality_score,
            file_path = excluded.file_path,
            trace_thread_id = excluded.trace_thread_id,
            trace_metadata = excluded.trace_metadata,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
        """,
        (
            session_id,
            industry,
            scenario,
            stage.value,
            status.value,
            requested_count,
            record_count,
            quality_score,
            file_path,
            trace_thread_id,
            json.dumps(trace_metadata, ensure_ascii=False) if trace_metadata else None,
            error_message,
            now if status in {SessionStatus.pending, SessionStatus.processing} else None,
            now if status in {SessionStatus.completed, SessionStatus.failed, SessionStatus.cancelled} else None,
            now,
            now,
        ),
    )
    await conn.commit()


def _parse_quality_detail(raw: str | None) -> QualityScore | None:
    if not raw:
        return None
    try:
        return QualityScore.model_validate_json(raw)
    except (ValueError, TypeError) as e:
        logger.debug("parse quality_detail failed: %s", e)
        return None


async def complete_session(
    session_id: str,
    scenario: str,
    record_count: int,
    file_path: str,
    quality: QualityScore,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    qj = quality.model_dump_json()
    conn = await get_connection()
    await conn.execute(
        """
        UPDATE traffic_sessions
        SET status = ?,
            scenario = ?,
            record_count = ?,
            quality_score = ?,
            file_path = ?,
            quality_detail = ?,
            error_message = NULL,
            completed_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            SessionStatus.completed.value,
            scenario,
            record_count,
            float(quality.total_score),
            file_path,
            qj,
            now,
            now,
            session_id,
        ),
    )
    await conn.commit()


async def fail_session(session_id: str, error_message: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = await get_connection()
    await conn.execute(
        """
        UPDATE traffic_sessions
        SET status = ?, error_message = ?, completed_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (SessionStatus.failed.value, error_message, now, now, session_id),
    )
    await conn.commit()


async def update_status(session_id: str, status: SessionStatus) -> None:
    logger.info(f"更新会话状态: session_id={session_id}, status={status.value}")
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = await get_connection()
        await conn.execute(
            """
            UPDATE traffic_sessions
            SET status = ?,
                completed_at = CASE
                    WHEN ? IN (?, ?, ?) THEN ?
                    ELSE completed_at
                END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                status.value,
                status.value,
                SessionStatus.completed.value,
                SessionStatus.failed.value,
                SessionStatus.cancelled.value,
                now,
                now,
                session_id,
            ),
        )
        await conn.commit()
        logger.info(f"会话状态更新成功: session_id={session_id}, status={status.value}")
    except Exception as e:
        logger.exception(f"更新会话状态失败: session_id={session_id}, error={e}")
        raise


async def get_session_file(session_id: str) -> str | None:
    logger.debug(f"获取会话文件: session_id={session_id}")
    try:
        conn = await get_connection()
        cursor = await conn.execute(
            "SELECT file_path FROM traffic_sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        file_path = row["file_path"] if row else None
        logger.debug(f"会话文件查询结果: session_id={session_id}, file_path={file_path}")
        return file_path
    except Exception as e:
        logger.exception(f"获取会话文件失败: session_id={session_id}, error={e}")
        raise


async def list_history(
    page: int,
    page_size: int,
    *,
    keyword: str | None = None,
    industry: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_quality: float | None = None,
) -> tuple[int, list[SessionSummary]]:
    conditions: list[str] = []
    params: list[str | float] = []

    if keyword:
        kw = f"%{keyword}%"
        conditions.append("(id LIKE ? OR industry LIKE ? OR scenario LIKE ? OR error_message LIKE ?)")
        params.extend([kw, kw, kw, kw])
    if industry:
        conditions.append("industry = ?")
        params.append(industry)
    if stage:
        conditions.append("stage = ?")
        params.append(stage)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if date_from:
        conditions.append("updated_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("updated_at <= ?")
        params.append(f"{date_to}T23:59:59")
    if min_quality is not None:
        conditions.append("quality_score >= ?")
        params.append(min_quality)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    select_fields = """
        id, industry, scenario, stage, status, requested_count, record_count,
        quality_score, quality_detail, trace_thread_id, error_message, started_at, completed_at,
        created_at, updated_at
    """

    conn = await get_connection()
    cursor = await conn.execute(
        f"SELECT COUNT(*) AS c FROM traffic_sessions {where_clause}",
        params,
    )
    count_row = await cursor.fetchone()
    total = count_row["c"]

    limit_offset = [page_size, (page - 1) * page_size]
    cursor = await conn.execute(
        f"""
        SELECT {select_fields}
        FROM traffic_sessions
        {where_clause}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ? OFFSET ?
        """,
        params + limit_offset,
    )
    rows = await cursor.fetchall()

    result = [
        SessionSummary(
            session_id=row["id"],
            industry=row["industry"],
            scenario=row["scenario"],
            stage=Stage(row["stage"]),
            status=SessionStatus(row["status"]),
            requested_count=row["requested_count"],
            record_count=row["record_count"],
            quality_score=row["quality_score"],
            quality_detail=_parse_quality_detail(row["quality_detail"]),
            trace_thread_id=row["trace_thread_id"],
            error_message=row["error_message"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
    return total, result


async def delete_session(session_id: str) -> None:
    conn = await get_connection()
    await conn.execute("DELETE FROM traffic_sessions WHERE id = ?", (session_id,))
    await conn.commit()


async def create_batch(batch_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = await get_connection()
    await conn.execute(
        "INSERT INTO batch_sessions (batch_id, created_at) VALUES (?, ?)",
        (batch_id, now),
    )
    await conn.commit()


async def add_batch_task(
    batch_id: str,
    task_index: int,
    session_id: str,
    industry: str,
    stage: str,
    count: int,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = await get_connection()
    await conn.execute(
        """
        INSERT INTO batch_tasks (
            batch_id, task_index, session_id, industry, stage, count,
            status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (batch_id, task_index, session_id, industry, stage, count, now),
    )
    await conn.commit()


async def update_batch_task_status(
    batch_id: str,
    task_index: int,
    status: str,
    error_message: str | None = None,
) -> None:
    conn = await get_connection()
    if error_message:
        await conn.execute(
            """
            UPDATE batch_tasks
            SET status = ?, error_message = ?
            WHERE batch_id = ? AND task_index = ?
            """,
            (status, error_message, batch_id, task_index),
        )
    else:
        await conn.execute(
            """
            UPDATE batch_tasks
            SET status = ?
            WHERE batch_id = ? AND task_index = ?
            """,
            (status, batch_id, task_index),
        )
    await conn.commit()


async def get_batch_tasks(batch_id: str) -> list[dict]:
    conn = await get_connection()
    cursor = await conn.execute(
        """
        SELECT task_index, session_id, industry, stage, count, status, error_message
        FROM batch_tasks
        WHERE batch_id = ?
        ORDER BY task_index
        """,
        (batch_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
