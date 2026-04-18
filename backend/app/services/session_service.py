import logging
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
) -> None:
    logger.info(f"创建会话: session_id={session_id}, industry={industry}, records={record_count}")
    
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO traffic_sessions (id, industry, scenario, stage, status, record_count, quality_score, file_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                industry,
                scenario,
                stage.value,
                status.value,
                record_count,
                quality_score,
                file_path,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def update_status(session_id: str, status: SessionStatus) -> None:
    logger.info(f"更新会话状态: session_id={session_id}, status={status.value}")
    
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE traffic_sessions SET status = ? WHERE id = ?",
                (status.value, session_id),
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
            SELECT id, industry, scenario, stage, status, record_count, quality_score, created_at
            FROM traffic_sessions
            ORDER BY created_at DESC
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
            record_count=row["record_count"],
            quality_score=row["quality_score"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return total, result


def delete_session(session_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM traffic_sessions WHERE id = ?", (session_id,))
        conn.commit()
