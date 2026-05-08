import aiosqlite
from pathlib import Path

from app.core.config import settings

_connection: aiosqlite.Connection | None = None

_SESSION_COLUMNS = {
    "requested_count": "INTEGER NOT NULL DEFAULT 0",
    "trace_thread_id": "TEXT",
    "trace_metadata": "TEXT",
    "error_message": "TEXT",
    "started_at": "TEXT",
    "completed_at": "TEXT",
    "updated_at": "TEXT",
    "quality_detail": "TEXT",
}


async def get_connection() -> aiosqlite.Connection:
    global _connection
    if _connection is None:
        db_path = Path(settings.sqlite_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _connection = await aiosqlite.connect(str(db_path))
        _connection.row_factory = aiosqlite.Row
    return _connection


async def init_db() -> None:
    conn = await get_connection()
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traffic_sessions (
            id TEXT PRIMARY KEY,
            industry TEXT NOT NULL,
            scenario TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_count INTEGER NOT NULL DEFAULT 0,
            record_count INTEGER NOT NULL,
            quality_score REAL,
            file_path TEXT,
            trace_thread_id TEXT,
            trace_metadata TEXT,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """
    )
    cursor = await conn.execute("PRAGMA table_info(traffic_sessions)")
    rows = await cursor.fetchall()
    existing_columns = {row["name"] for row in rows}
    for column, definition in _SESSION_COLUMNS.items():
        if column not in existing_columns:
            await conn.execute(f"ALTER TABLE traffic_sessions ADD COLUMN {column} {definition}")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_sessions (
            batch_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            task_index INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            industry TEXT NOT NULL,
            stage TEXT NOT NULL,
            count INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (batch_id) REFERENCES batch_sessions(batch_id)
        )
        """
    )
    await conn.commit()
