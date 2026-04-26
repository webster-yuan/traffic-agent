import sqlite3
import threading
from pathlib import Path

from app.core.config import settings

_thread_local = threading.local()

_SESSION_COLUMNS = {
    "requested_count": "INTEGER NOT NULL DEFAULT 0",
    "trace_thread_id": "TEXT",
    "trace_metadata": "TEXT",
    "error_message": "TEXT",
    "started_at": "TEXT",
    "completed_at": "TEXT",
    "updated_at": "TEXT",
}


def get_connection() -> sqlite3.Connection:
    if not hasattr(_thread_local, "conn"):
        db_path = Path(settings.sqlite_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _thread_local.conn = conn
    return _thread_local.conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
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
        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(traffic_sessions)").fetchall()
        }
        for column, definition in _SESSION_COLUMNS.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE traffic_sessions ADD COLUMN {column} {definition}")
        conn.commit()
