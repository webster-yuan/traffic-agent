import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import uuid

from app.db.database import get_connection, init_db

pytestmark = pytest.mark.asyncio


async def test_init_db_creates_table():
    await init_db()
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='traffic_sessions'"
    )
    result = await cursor.fetchone()
    assert result is not None
    assert result[0] == "traffic_sessions"


async def test_connection_cached():
    conn1 = await get_connection()
    conn2 = await get_connection()
    assert conn1 is conn2


async def test_init_db_creates_all_tables():
    await init_db()
    conn = await get_connection()
    for table in ["traffic_sessions", "batch_sessions", "batch_tasks"]:
        cursor = await conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
        )
        result = await cursor.fetchone()
        assert result is not None, f"Table {table} should exist"
        assert result[0] == table


async def test_schema_integrity():
    await init_db()
    conn = await get_connection()
    cursor = await conn.execute("PRAGMA table_info(traffic_sessions)")
    rows = await cursor.fetchall()
    columns = {row["name"] for row in rows}

    expected_columns = {
        "id", "industry", "scenario", "stage", "status",
        "requested_count", "record_count", "quality_score", "file_path",
        "quality_detail", "trace_thread_id", "trace_metadata", "error_message", "started_at",
        "completed_at", "created_at", "updated_at"
    }

    assert columns == expected_columns, f"Expected {expected_columns}, got {columns}"
