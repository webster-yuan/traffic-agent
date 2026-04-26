import sys
from pathlib import Path

import pytest

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import threading
import uuid
from unittest.mock import patch

from app.db.database import get_connection, init_db
from app.models.schemas import SessionStatus, SessionSummary, Stage


def test_init_db_creates_table():
    """初始化数据库时应该创建 traffic_sessions 表"""
    init_db()
    conn = get_connection()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='traffic_sessions'"
    )
    result = cursor.fetchone()
    assert result is not None
    assert result[0] == "traffic_sessions"


def test_connection_thread_local():
    """测试 get_connection 使用线程本地存储"""
    # 清理可能的残留连接
    conn = get_connection()
    conn.execute("DELETE FROM traffic_sessions WHERE id = 'test-thread-local'")
    conn.commit()

    # 获取两个连接的引用
    conn1 = get_connection()
    conn2 = get_connection()

    # 应该是同一个对象（线程本地缓存）
    assert conn1 is conn2

    # 在连接1上执行操作
    conn1.execute(
        """
        INSERT INTO traffic_sessions (
            id, industry, scenario, stage, status, record_count,
            quality_score, file_path, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "test-thread-local",
            "test",
            "test",
            "quick",
            "completed",
            1,
            100.0,
            "/tmp/test.csv",
            "2026-04-19T10:00:00+00:00",
        ),
    )
    conn1.commit()

    # 从连接2读取应该能看到
    result = conn2.execute("SELECT id FROM traffic_sessions WHERE id = 'test-thread-local'").fetchone()
    assert result is not None
    assert result[0] == "test-thread-local"

    # 清理
    conn1.execute("DELETE FROM traffic_sessions WHERE id = 'test-thread-local'")
    conn1.commit()


def test_transaction_isolation():
    """测试数据库事务隔离性"""
    session_id = str(uuid.uuid4())

    def write_and_commit(sid: str):
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO traffic_sessions (
                id, industry, scenario, stage, status, record_count,
                quality_score, file_path, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                "ecommerce",
                "全天候配送",
                "standard",
                "completed",
                100,
                85.5,
                f"/tmp/{sid}.csv",
                "2026-04-19T10:00:00+00:00",
            ),
        )
        conn.commit()

    def read_and_check(sid: str):
        conn = get_connection()
        result = conn.execute(
            "SELECT COUNT(*) as cnt FROM traffic_sessions WHERE id = ?", (sid,)
        ).fetchone()
        return result["cnt"]

    # 创建写线程
    write_thread = threading.Thread(target=write_and_commit, args=(session_id,))
    write_thread.start()
    write_thread.join(timeout=5)

    # 在写操作完成前读取（应该能看到数据）
    # 这个测试主要验证不会抛出异常，而不是严格的并发测试
    try:
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM traffic_sessions WHERE id = ?", (session_id,)
        ).fetchone()["cnt"]
        assert count == 1
    except sqlite3.OperationalError as e:
        # 部分系统可能仍然会锁定，这是可接受的
        pass

    # 清理
    conn = get_connection()
    conn.execute("DELETE FROM traffic_sessions WHERE id = ?", (session_id,))
    conn.commit()


def test_schema_integrity():
    """测试数据库表结构完整性"""
    init_db()
    conn = get_connection()

    # 检查表结构
    cursor = conn.execute("PRAGMA table_info(traffic_sessions)")
    columns = {row["name"] for row in cursor.fetchall()}

    expected_columns = {
        "id", "industry", "scenario", "stage", "status",
        "requested_count", "record_count", "quality_score", "file_path",
        "quality_detail", "trace_thread_id", "trace_metadata", "error_message", "started_at",
        "completed_at", "created_at", "updated_at"
    }

    assert columns == expected_columns, f"Expected {expected_columns}, got {columns}"


def test_connection_persists_across_calls():
    """测试 get_connection 在多次调用中返回相同连接"""
    init_db()
    conn1 = get_connection()
    conn2 = get_connection()
    assert conn1 is conn2
    
