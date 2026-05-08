"""Tests for app.services.session_service — session CRUD operations."""

import uuid

import pytest
import pytest_asyncio

from app.db.database import get_connection, init_db
from app.models.schemas import QualityScore, SessionStatus, Stage
from app.services.session_service import (
    _parse_quality_detail,
    add_batch_task,
    complete_session,
    create_batch,
    create_session,
    delete_session,
    fail_session,
    get_batch_tasks,
    get_session_file,
    list_history,
    update_batch_task_status,
    update_status,
)

@pytest_asyncio.fixture(autouse=True)
async def _ensure_db():
    await init_db()


@pytest.fixture
def session_id() -> str:
    return uuid.uuid4().hex[:12]


async def _cleanup(sid: str):
    conn = await get_connection()
    await conn.execute("DELETE FROM traffic_sessions WHERE id = ?", (sid,))
    await conn.execute("DELETE FROM batch_tasks WHERE session_id = ?", (sid,))
    await conn.commit()


async def _count_sessions(sid: str) -> int:
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT COUNT(*) AS c FROM traffic_sessions WHERE id = ?", (sid,)
    )
    row = await cursor.fetchone()
    return row["c"]


# ── create_session ──────────────────────────────────────────────────

async def test_create_session_inserts_row(session_id):
    await create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="flash_sale",
        stage=Stage.standard,
        status=SessionStatus.pending,
        record_count=0,
        quality_score=None,
        file_path=None,
        requested_count=100,
    )
    assert await _count_sessions(session_id) == 1
    await _cleanup(session_id)


async def test_create_session_upserts_on_conflict(session_id):
    await create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="first",
        stage=Stage.quick,
        status=SessionStatus.pending,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    await create_session(
        session_id=session_id,
        industry="finance",
        scenario="second",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=50,
        quality_score=80.0,
        file_path="/tmp/test.json",
    )
    assert await _count_sessions(session_id) == 1
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT industry, scenario, stage, status, record_count FROM traffic_sessions WHERE id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    assert row["industry"] == "finance"
    assert row["scenario"] == "second"
    assert row["stage"] == "standard"
    assert row["status"] == "processing"
    assert row["record_count"] == 50
    await _cleanup(session_id)


async def test_create_session_with_trace_metadata(session_id):
    meta = {"thread_id": "abc123", "tags": ["test"]}
    await create_session(
        session_id=session_id,
        industry="gaming",
        scenario="login",
        stage=Stage.quick,
        status=SessionStatus.pending,
        record_count=0,
        quality_score=None,
        file_path=None,
        trace_thread_id="thread-1",
        trace_metadata=meta,
    )
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT trace_thread_id, trace_metadata FROM traffic_sessions WHERE id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    assert row["trace_thread_id"] == "thread-1"
    assert "abc123" in row["trace_metadata"]
    await _cleanup(session_id)


async def test_create_session_with_error_message(session_id):
    await create_session(
        session_id=session_id,
        industry="media",
        scenario="streaming",
        stage=Stage.quick,
        status=SessionStatus.failed,
        record_count=0,
        quality_score=None,
        file_path=None,
        error_message="LLM timeout",
    )
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT error_message FROM traffic_sessions WHERE id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    assert row["error_message"] == "LLM timeout"
    await _cleanup(session_id)


# ── complete_session ────────────────────────────────────────────────

async def test_complete_session_updates_fields(session_id):
    await create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    quality = QualityScore(
        format_score=90, business_score=85, diversity_score=80,
        total_score=85, passed=True,
    )
    await complete_session(
        session_id=session_id,
        scenario="updated_scenario",
        record_count=100,
        file_path="/tmp/out.json",
        quality=quality,
    )
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT status, scenario, record_count, quality_score, file_path "
        "FROM traffic_sessions WHERE id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    assert row["status"] == "completed"
    assert row["scenario"] == "updated_scenario"
    assert row["record_count"] == 100
    assert row["quality_score"] == 85.0
    assert row["file_path"] == "/tmp/out.json"
    await _cleanup(session_id)


# ── fail_session ────────────────────────────────────────────────────

async def test_fail_session_sets_error(session_id):
    await create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    await fail_session(session_id, "network error")
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT status, error_message FROM traffic_sessions WHERE id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    assert row["status"] == "failed"
    assert row["error_message"] == "network error"
    await _cleanup(session_id)


# ── update_status ───────────────────────────────────────────────────

async def test_update_status_to_cancelled(session_id):
    await create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    await update_status(session_id, SessionStatus.cancelled)
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT status FROM traffic_sessions WHERE id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    assert row["status"] == "cancelled"
    await _cleanup(session_id)


async def test_update_status_to_completed(session_id):
    await create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    await update_status(session_id, SessionStatus.completed)
    conn = await get_connection()
    cursor = await conn.execute(
        "SELECT status FROM traffic_sessions WHERE id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    assert row["status"] == "completed"
    await _cleanup(session_id)


# ── get_session_file ────────────────────────────────────────────────

async def test_get_session_file_returns_path(session_id):
    await create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.completed,
        record_count=100,
        quality_score=85.0,
        file_path="/tmp/data.json",
    )
    path = await get_session_file(session_id)
    assert path == "/tmp/data.json"
    await _cleanup(session_id)


async def test_get_session_file_returns_none_for_missing(session_id):
    path = await get_session_file("nonexistent-id")
    assert path is None


# ── delete_session ──────────────────────────────────────────────────

async def test_delete_session_removes_row(session_id):
    await create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.quick,
        status=SessionStatus.pending,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    assert await _count_sessions(session_id) == 1
    await delete_session(session_id)
    assert await _count_sessions(session_id) == 0


# ── list_history ────────────────────────────────────────────────────

async def test_list_history_returns_sessions(session_id):
    await create_session(
        session_id=session_id,
        industry="finance",
        scenario="payment",
        stage=Stage.standard,
        status=SessionStatus.completed,
        record_count=50,
        quality_score=90.0,
        file_path="/tmp/fin.json",
    )
    total, items = await list_history(page=1, page_size=10)
    assert total >= 1
    assert any(s.session_id == session_id for s in items)
    await _cleanup(session_id)


async def test_list_history_filters_by_industry(session_id):
    await create_session(
        session_id=session_id,
        industry="gaming",
        scenario="match",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = await list_history(page=1, page_size=10, industry="gaming")
    assert total >= 1
    assert all(s.industry == "gaming" for s in items)
    await _cleanup(session_id)


async def test_list_history_filters_by_status(session_id):
    await create_session(
        session_id=session_id,
        industry="media",
        scenario="video",
        stage=Stage.quick,
        status=SessionStatus.failed,
        record_count=0,
        quality_score=None,
        file_path=None,
        error_message="timeout",
    )
    total, items = await list_history(page=1, page_size=10, status="failed")
    assert total >= 1
    assert all(s.status == SessionStatus.failed for s in items)
    await _cleanup(session_id)


async def test_list_history_pagination(session_id):
    await create_session(
        session_id=session_id,
        industry="media",
        scenario="pagination",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=5,
        quality_score=70.0,
        file_path=None,
    )
    total, items = await list_history(page=1, page_size=1)
    assert len(items) <= 1
    await _cleanup(session_id)


# ── batch operations ────────────────────────────────────────────────

async def test_create_and_get_batch_tasks(session_id):
    batch_id = uuid.uuid4().hex[:8]
    await create_batch(batch_id)
    await add_batch_task(batch_id, 0, session_id, "ecommerce", "standard", 100)
    tasks = await get_batch_tasks(batch_id)
    assert len(tasks) == 1
    assert tasks[0]["session_id"] == session_id
    assert tasks[0]["status"] == "pending"
    conn = await get_connection()
    await conn.execute("DELETE FROM batch_tasks WHERE batch_id = ?", (batch_id,))
    await conn.execute("DELETE FROM batch_sessions WHERE batch_id = ?", (batch_id,))
    await conn.commit()


async def test_update_batch_task_status(session_id):
    batch_id = uuid.uuid4().hex[:8]
    await create_batch(batch_id)
    await add_batch_task(batch_id, 0, session_id, "gaming", "quick", 50)
    await update_batch_task_status(batch_id, 0, "completed")
    tasks = await get_batch_tasks(batch_id)
    assert tasks[0]["status"] == "completed"
    conn = await get_connection()
    await conn.execute("DELETE FROM batch_tasks WHERE batch_id = ?", (batch_id,))
    await conn.execute("DELETE FROM batch_sessions WHERE batch_id = ?", (batch_id,))
    await conn.commit()


async def test_update_batch_task_status_with_error(session_id):
    batch_id = uuid.uuid4().hex[:8]
    await create_batch(batch_id)
    await add_batch_task(batch_id, 0, session_id, "gaming", "quick", 50)
    await update_batch_task_status(batch_id, 0, "failed", error_message="crash")
    tasks = await get_batch_tasks(batch_id)
    assert tasks[0]["status"] == "failed"
    assert tasks[0]["error_message"] == "crash"
    conn = await get_connection()
    await conn.execute("DELETE FROM batch_tasks WHERE batch_id = ?", (batch_id,))
    await conn.execute("DELETE FROM batch_sessions WHERE batch_id = ?", (batch_id,))
    await conn.commit()


# ── _parse_quality_detail (sync, no DB) ─────────────────────────────

def test_parse_quality_detail_valid_json():
    score = QualityScore(
        format_score=90, business_score=85, diversity_score=80,
        total_score=85, passed=True,
    )
    result = _parse_quality_detail(score.model_dump_json())
    assert result is not None
    assert result.total_score == 85.0


def test_parse_quality_detail_none_returns_none():
    assert _parse_quality_detail(None) is None


def test_parse_quality_detail_empty_string_returns_none():
    assert _parse_quality_detail("") is None


def test_parse_quality_detail_invalid_json_returns_none():
    assert _parse_quality_detail("not valid") is None


# ── list_history additional filters ─────────────────────────────────

async def test_list_history_keyword_filter(session_id):
    await create_session(
        session_id=session_id,
        industry="healthcare",
        scenario="patient_portal",
        stage=Stage.standard,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = await list_history(page=1, page_size=10, keyword="patient")
    assert any(s.session_id == session_id for s in items)
    await _cleanup(session_id)


async def test_list_history_stage_filter(session_id):
    await create_session(
        session_id=session_id,
        industry="logistics",
        scenario="tracking",
        stage=Stage.full,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = await list_history(page=1, page_size=10, stage="full")
    assert all(s.stage == Stage.full for s in items)
    await _cleanup(session_id)


async def test_list_history_min_quality_filter(session_id):
    await create_session(
        session_id=session_id,
        industry="delivery",
        scenario="tracking",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=90.0,
        file_path=None,
    )
    total, items = await list_history(page=1, page_size=10, min_quality=80.0)
    assert any(s.session_id == session_id for s in items)
    await _cleanup(session_id)


async def test_update_status_non_existent_no_crash(session_id):
    await create_session(
        session_id=session_id,
        industry="social",
        scenario="feed",
        stage=Stage.quick,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    await update_status("nonexistent_99999", SessionStatus.cancelled)
    await _cleanup(session_id)


async def test_get_session_file_missing_no_crash(session_id):
    result = await get_session_file("nonexistent_abcde")
    assert result is None


async def test_list_history_date_from_filter(session_id):
    await create_session(
        session_id=session_id,
        industry="social",
        scenario="feed",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = await list_history(page=1, page_size=10, date_from="2020-01-01")
    assert any(s.session_id == session_id for s in items)
    await _cleanup(session_id)


async def test_list_history_date_to_filter(session_id):
    await create_session(
        session_id=session_id,
        industry="social",
        scenario="feed",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = await list_history(page=1, page_size=10, date_to="2099-12-31")
    assert any(s.session_id == session_id for s in items)
    await _cleanup(session_id)
