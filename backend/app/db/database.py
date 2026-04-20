import sqlite3
import threading
from pathlib import Path

from app.core.config import settings

_thread_local = threading.local()


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
                record_count INTEGER NOT NULL,
                quality_score REAL,
                file_path TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
