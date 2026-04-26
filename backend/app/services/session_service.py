import logging
import json
from datetime import datetime, timezone

from app.db.database import get_connection
from app.models.schemas import SessionStatus, SessionSummary, Stage

logger = logging.getLogger(__name__)


def create_session(
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
    
    with get_connection() as conn:
        conn.execute(
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
        conn.commit()


def complete_session(
    session_id: str,
    scenario: str,
    record_count: int,
    quality_score: float,
    file_path: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE traffic_sessions
            SET status = ?,
                scenario = ?,
                record_count = ?,
                quality_score = ?,
                file_path = ?,
                error_message = NULL,
                completed_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                SessionStatus.completed.value,
                scenario,
                record_count,
                quality_score,
                file_path,
                now,
                now,
                session_id,
            ),
        )
        conn.commit()


def fail_session(session_id: str, error_message: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE traffic_sessions
            SET status = ?, error_message = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (SessionStatus.failed.value, error_message, now, now, session_id),
        )
        conn.commit()


def update_status(session_id: str, status: SessionStatus) -> None:
    logger.info(f"更新会话状态: session_id={session_id}, status={status.value}")
    now = datetime.now(timezone.utc).isoformat()
    
    try:
        with get_connection() as conn:
            conn.execute(
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
            conn.commit()
        logger.info(f"会话状态更新成功: session_id={session_id}, status={status.value}")
    except Exception as e:
        logger.exception(f"更新会话状态失败: session_id={session_id}, error={e}")
        raise


def get_session_file(session_id: str) -> str | None:
    logger.debug(f"获取会话文件: session_id={session_id}")
    
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT file_path FROM traffic_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        file_path = row["file_path"] if row else None
        logger.debug(f"会话文件查询结果: session_id={session_id}, file_path={file_path}")
        return file_path
    except Exception as e:
        logger.exception(f"获取会话文件失败: session_id={session_id}, error={e}")
        raise


def list_history(page: int, page_size: int) -> tuple[int, list[SessionSummary]]:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM traffic_sessions").fetchone()["c"]
        rows = conn.execute(
            """
            SELECT
                id, industry, scenario, stage, status, requested_count, record_count,
                quality_score, trace_thread_id, error_message, started_at, completed_at,
                created_at, updated_at
            FROM traffic_sessions
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, (page - 1) * page_size),
        ).fetchall()
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


def delete_session(session_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM traffic_sessions WHERE id = ?", (session_id,))
        conn.commit()
