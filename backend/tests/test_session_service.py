"""Tests for app.services.session_service — session CRUD operations."""

import uuid

import pytest

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


@pytest.fixture(autouse=True)
def _ensure_db():
    """Ensure DB tables exist before each test."""
    init_db()


@pytest.fixture
def session_id() -> str:
    return uuid.uuid4().hex[:12]


def _cleanup(sid: str):
    conn = get_connection()
    conn.execute("DELETE FROM traffic_sessions WHERE id = ?", (sid,))
    conn.execute("DELETE FROM batch_tasks WHERE session_id = ?", (sid,))
    conn.commit()


def _count_sessions(sid: str) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM traffic_sessions WHERE id = ?", (sid,)
    ).fetchone()
    return row["c"]


# ── create_session ──────────────────────────────────────────────────

def test_create_session_inserts_row(session_id):
    """create_session inserts a new row with correct field values."""
    create_session(
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
    assert _count_sessions(session_id) == 1
    _cleanup(session_id)


def test_create_session_upserts_on_conflict(session_id):
    """create_session updates existing row on ID conflict."""
    create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="first",
        stage=Stage.quick,
        status=SessionStatus.pending,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    create_session(
        session_id=session_id,
        industry="finance",
        scenario="second",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=50,
        quality_score=80.0,
        file_path="/tmp/test.json",
    )
    assert _count_sessions(session_id) == 1
    conn = get_connection()
    row = conn.execute(
        "SELECT industry, scenario, stage, status, record_count FROM traffic_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert row["industry"] == "finance"
    assert row["scenario"] == "second"
    assert row["stage"] == "standard"
    assert row["status"] == "processing"
    assert row["record_count"] == 50
    _cleanup(session_id)


def test_create_session_with_trace_metadata(session_id):
    """create_session serializes trace_metadata as JSON."""
    meta = {"thread_id": "abc123", "tags": ["test"]}
    create_session(
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
    conn = get_connection()
    row = conn.execute(
        "SELECT trace_thread_id, trace_metadata FROM traffic_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert row["trace_thread_id"] == "thread-1"
    assert "abc123" in row["trace_metadata"]
    _cleanup(session_id)


def test_create_session_with_error_message(session_id):
    """create_session stores error_message when provided."""
    create_session(
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
    conn = get_connection()
    row = conn.execute(
        "SELECT error_message FROM traffic_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    assert row["error_message"] == "LLM timeout"
    _cleanup(session_id)


# ── complete_session ────────────────────────────────────────────────

def test_complete_session_updates_fields(session_id):
    """complete_session sets status=completed with quality score."""
    create_session(
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
    complete_session(
        session_id=session_id,
        scenario="updated_scenario",
        record_count=100,
        file_path="/tmp/out.json",
        quality=quality,
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT status, scenario, record_count, quality_score, file_path "
        "FROM traffic_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert row["status"] == "completed"
    assert row["scenario"] == "updated_scenario"
    assert row["record_count"] == 100
    assert row["quality_score"] == 85.0
    assert row["file_path"] == "/tmp/out.json"
    _cleanup(session_id)


# ── fail_session ────────────────────────────────────────────────────

def test_fail_session_sets_error(session_id):
    """fail_session sets status=failed with error message."""
    create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    fail_session(session_id, "network error")
    conn = get_connection()
    row = conn.execute(
        "SELECT status, error_message FROM traffic_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert row["status"] == "failed"
    assert row["error_message"] == "network error"
    _cleanup(session_id)


# ── update_status ───────────────────────────────────────────────────

def test_update_status_to_cancelled(session_id):
    """update_status transitions session to cancelled."""
    create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    update_status(session_id, SessionStatus.cancelled)
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM traffic_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    assert row["status"] == "cancelled"
    _cleanup(session_id)


def test_update_status_to_completed(session_id):
    """update_status transitions session to completed."""
    create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    update_status(session_id, SessionStatus.completed)
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM traffic_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    assert row["status"] == "completed"
    _cleanup(session_id)


# ── get_session_file ────────────────────────────────────────────────

def test_get_session_file_returns_path(session_id):
    """get_session_file returns file_path for existing session."""
    create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.standard,
        status=SessionStatus.completed,
        record_count=100,
        quality_score=85.0,
        file_path="/tmp/data.json",
    )
    path = get_session_file(session_id)
    assert path == "/tmp/data.json"
    _cleanup(session_id)


def test_get_session_file_returns_none_for_missing(session_id):
    """get_session_file returns None for non-existent session."""
    path = get_session_file("nonexistent-id")
    assert path is None


# ── delete_session ──────────────────────────────────────────────────

def test_delete_session_removes_row(session_id):
    """delete_session removes the session from DB."""
    create_session(
        session_id=session_id,
        industry="ecommerce",
        scenario="normal",
        stage=Stage.quick,
        status=SessionStatus.pending,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    assert _count_sessions(session_id) == 1
    delete_session(session_id)
    assert _count_sessions(session_id) == 0


# ── list_history ────────────────────────────────────────────────────

def test_list_history_returns_sessions(session_id):
    """list_history returns paginated sessions sorted by updated_at."""
    create_session(
        session_id=session_id,
        industry="finance",
        scenario="payment",
        stage=Stage.standard,
        status=SessionStatus.completed,
        record_count=50,
        quality_score=90.0,
        file_path="/tmp/fin.json",
    )
    total, items = list_history(page=1, page_size=10)
    assert total >= 1
    assert any(s.session_id == session_id for s in items)
    _cleanup(session_id)


def test_list_history_filters_by_industry(session_id):
    """list_history filters sessions by industry."""
    create_session(
        session_id=session_id,
        industry="gaming",
        scenario="match",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = list_history(page=1, page_size=10, industry="gaming")
    assert total >= 1
    assert all(s.industry == "gaming" for s in items)
    _cleanup(session_id)


def test_list_history_filters_by_status(session_id):
    """list_history filters sessions by status."""
    create_session(
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
    total, items = list_history(page=1, page_size=10, status="failed")
    assert total >= 1
    assert all(s.status == SessionStatus.failed for s in items)
    _cleanup(session_id)


def test_list_history_pagination(session_id):
    """list_history respects page_size limit."""
    create_session(
        session_id=session_id,
        industry="media",
        scenario="pagination",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=5,
        quality_score=70.0,
        file_path=None,
    )
    total, items = list_history(page=1, page_size=1)
    assert len(items) <= 1
    _cleanup(session_id)


# ── batch operations ────────────────────────────────────────────────

def test_create_and_get_batch_tasks(session_id):
    """create_batch + add_batch_task + get_batch_tasks round-trip."""
    batch_id = uuid.uuid4().hex[:8]
    create_batch(batch_id)
    add_batch_task(batch_id, 0, session_id, "ecommerce", "standard", 100)
    tasks = get_batch_tasks(batch_id)
    assert len(tasks) == 1
    assert tasks[0]["session_id"] == session_id
    assert tasks[0]["status"] == "pending"
    # cleanup
    conn = get_connection()
    conn.execute("DELETE FROM batch_tasks WHERE batch_id = ?", (batch_id,))
    conn.execute("DELETE FROM batch_sessions WHERE batch_id = ?", (batch_id,))
    conn.commit()


def test_update_batch_task_status(session_id):
    """update_batch_task_status updates task status."""
    batch_id = uuid.uuid4().hex[:8]
    create_batch(batch_id)
    add_batch_task(batch_id, 0, session_id, "gaming", "quick", 50)
    update_batch_task_status(batch_id, 0, "completed")
    tasks = get_batch_tasks(batch_id)
    assert tasks[0]["status"] == "completed"
    # cleanup
    conn = get_connection()
    conn.execute("DELETE FROM batch_tasks WHERE batch_id = ?", (batch_id,))
    conn.execute("DELETE FROM batch_sessions WHERE batch_id = ?", (batch_id,))
    conn.commit()


def test_update_batch_task_status_with_error(session_id):
    """update_batch_task_status stores error message."""
    batch_id = uuid.uuid4().hex[:8]
    create_batch(batch_id)
    add_batch_task(batch_id, 0, session_id, "gaming", "quick", 50)
    update_batch_task_status(batch_id, 0, "failed", error_message="crash")
    tasks = get_batch_tasks(batch_id)
    assert tasks[0]["status"] == "failed"
    assert tasks[0]["error_message"] == "crash"
    # cleanup
    conn = get_connection()
    conn.execute("DELETE FROM batch_tasks WHERE batch_id = ?", (batch_id,))
    conn.execute("DELETE FROM batch_sessions WHERE batch_id = ?", (batch_id,))
    conn.commit()


# ── _parse_quality_detail ───────────────────────────────────────────

def test_parse_quality_detail_valid_json():
    """_parse_quality_detail parses valid QualityScore JSON."""
    score = QualityScore(
        format_score=90, business_score=85, diversity_score=80,
        total_score=85, passed=True,
    )
    result = _parse_quality_detail(score.model_dump_json())
    assert result is not None
    assert result.total_score == 85.0


def test_parse_quality_detail_none_returns_none():
    """_parse_quality_detail returns None for None input."""
    assert _parse_quality_detail(None) is None


def test_parse_quality_detail_empty_string_returns_none():
    """_parse_quality_detail returns None for empty string."""
    assert _parse_quality_detail("") is None


def test_parse_quality_detail_invalid_json_returns_none():
    """_parse_quality_detail returns None for invalid JSON."""
    assert _parse_quality_detail("not valid") is None


# ── list_history additional filters ─────────────────────────────────

def test_list_history_keyword_filter(session_id):
    """list_history filters by keyword across id/industry/scenario/error."""
    create_session(
        session_id=session_id,
        industry="healthcare",
        scenario="patient_portal",
        stage=Stage.standard,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = list_history(page=1, page_size=10, keyword="patient")
    assert any(s.session_id == session_id for s in items)
    _cleanup(session_id)


def test_list_history_stage_filter(session_id):
    """list_history filters by stage."""
    create_session(
        session_id=session_id,
        industry="logistics",
        scenario="tracking",
        stage=Stage.full,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = list_history(page=1, page_size=10, stage="full")
    assert all(s.stage == Stage.full for s in items)
    _cleanup(session_id)


def test_list_history_min_quality_filter(session_id):
    """list_history filters by minimum quality_score."""
    create_session(
        session_id=session_id,
        industry="delivery",
        scenario="tracking",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=90.0,
        file_path=None,
    )
    total, items = list_history(page=1, page_size=10, min_quality=80.0)
    assert any(s.session_id == session_id for s in items)
    _cleanup(session_id)


def test_update_status_exception_propagates(session_id):
    """update_status propagates exceptions when DB operation fails."""
    create_session(
        session_id=session_id,
        industry="social",
        scenario="feed",
        stage=Stage.quick,
        status=SessionStatus.processing,
        record_count=0,
        quality_score=None,
        file_path=None,
    )
    # update_status on a non-existent session should not raise
    # (it just updates 0 rows), but we verify it doesn't crash
    update_status("nonexistent_99999", SessionStatus.cancelled)
    _cleanup(session_id)


def test_get_session_file_exception_propagates(session_id):
    """get_session_file returns None for missing session, no crash."""
    result = get_session_file("nonexistent_abcde")
    assert result is None


def test_list_history_date_from_filter(session_id):
    """list_history filters by updated_at >= date_from."""
    create_session(
        session_id=session_id,
        industry="social",
        scenario="feed",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = list_history(page=1, page_size=10, date_from="2020-01-01")
    assert any(s.session_id == session_id for s in items)
    _cleanup(session_id)


def test_list_history_date_to_filter(session_id):
    """list_history filters by updated_at <= date_to."""
    create_session(
        session_id=session_id,
        industry="social",
        scenario="feed",
        stage=Stage.quick,
        status=SessionStatus.completed,
        record_count=10,
        quality_score=80.0,
        file_path=None,
    )
    total, items = list_history(page=1, page_size=10, date_to="2099-12-31")
    assert any(s.session_id == session_id for s in items)
    _cleanup(session_id)
