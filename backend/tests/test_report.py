"""Tests for HTML report generation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import QualityScore
from app.services.report_service import generate_report_html


def _make_quality(score: float = 85.0) -> QualityScore:
    return QualityScore(
        format_score=90.0,
        business_score=80.0,
        diversity_score=85.0,
        total_score=score,
        passed=score >= 70.0,
        format_notes=["IP 地址范围合理"],
        business_notes=["URL 与行业匹配"],
        diversity_notes=["User-Agent 多样性一般"],
    )


MOCK_ROW = {
    "id": "abc123",
    "industry": "ride_hailing",
    "scenario": "通勤高峰",
    "stage": "quick",
    "status": "completed",
    "requested_count": 10,
    "record_count": 2,
    "quality_score": 89.0,
    "quality_detail": _make_quality(89.0).model_dump_json(),
    "trace_thread_id": "thread-1",
    "error_message": None,
    "started_at": "2026-04-29T10:00:00+00:00",
    "completed_at": "2026-04-29T10:01:00+00:00",
    "created_at": "2026-04-29T10:00:00+00:00",
    "updated_at": "2026-04-29T10:01:00+00:00",
    "file_path": "/tmp/output/traffic_ride_hailing_abc123.csv",
}

MOCK_RECORDS = [
    {
        "id": "1", "method": "GET", "url": "/api/v1/drivers",
        "status_code": 200, "timestamp": "2026-04-29T10:00:01Z",
        "src_ip": "10.0.1.5", "src_port": 44321, "dst_ip": "192.168.1.1",
        "dst_port": 443, "header": {"Host": "api.example.com"},
        "req_body": None, "resp_body": {"drivers": []},
        "rtt": 12.5, "duration": None, "user_agent": "TrafficAgent/1.0",
        "referer": None, "identity_label": "real",
    },
    {
        "id": "2", "method": "POST", "url": "/api/v1/orders",
        "status_code": 201, "timestamp": "2026-04-29T10:00:02Z",
        "src_ip": "10.0.2.8", "src_port": 55123, "dst_ip": "192.168.1.1",
        "dst_port": 443, "header": {"Host": "api.example.com", "Content-Type": "application/json"},
        "req_body": {"item": "test"}, "resp_body": {"order_id": "ord-1"},
        "rtt": 8.2, "duration": None, "user_agent": "Mozilla/5.0",
        "referer": None, "identity_label": "fake",
    },
]


def _make_async_mock_conn(fetchone_result):
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=fetchone_result)
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    return mock_conn


@pytest.mark.asyncio
async def test_report_404_for_unknown_session():
    with patch("app.services.report_service.get_connection") as mock_get_conn:
        mock_get_conn.return_value = _make_async_mock_conn(None)
        result = await generate_report_html("no_such_session")
    assert result is None


@pytest.mark.asyncio
async def test_report_generates_html_for_completed_session():
    with patch("app.services.report_service.get_connection") as mock_get_conn, \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.read_text") as mock_read:
        mock_get_conn.return_value = _make_async_mock_conn(MOCK_ROW)
        mock_read.return_value = json.dumps({
            "metadata": {}, "records": MOCK_RECORDS,
        }, ensure_ascii=False)

        html = await generate_report_html("abc123")

    assert html is not None
    assert "<!DOCTYPE html>" in html
    assert "Traffic Agent 生成报告" in html
    assert "abc123" in html
    assert "ride_hailing" in html
    assert "真实流量" in html
    assert "脚本流量" in html
    assert "GET" in html
    assert "echarts.min.js" in html
    assert "通过" in html
    assert "Traffic Agent" in html


@pytest.mark.asyncio
async def test_report_includes_error_for_failed_session():
    row = dict(MOCK_ROW)
    row["status"] = "failed"
    row["error_message"] = "LLM timeout after 3 retries"
    row.pop("quality_score", None)
    row["quality_detail"] = None
    row["file_path"] = None

    with patch("app.services.report_service.get_connection") as mock_get_conn:
        mock_get_conn.return_value = _make_async_mock_conn(row)
        html = await generate_report_html("abc123")

    assert html is not None
    assert "failed" in html
    assert "LLM timeout after 3 retries" in html
    assert "错误信息" in html


@pytest.mark.asyncio
async def test_report_no_json_file_fallback():
    with patch("app.services.report_service.get_connection") as mock_get_conn, \
         patch("pathlib.Path.exists", return_value=False):
        mock_get_conn.return_value = _make_async_mock_conn(MOCK_ROW)
        html = await generate_report_html("abc123")

    assert html is not None
    assert "<!DOCTYPE html>" in html
    assert "样本记录" not in html


def test_report_endpoint_returns_html():
    client = TestClient(app)
    with patch("app.api.observability.generate_report_html") as mock_gen:
        mock_gen.return_value = "<html><body>Test</body></html>"
        resp = client.get("/api/v1/traffic/report/abc123")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<html>" in resp.text


def test_report_endpoint_404():
    client = TestClient(app)
    with patch("app.api.observability.generate_report_html", return_value=None):
        resp = client.get("/api/v1/traffic/report/no_such_session")

    assert resp.status_code == 404
    assert "会话不存在" in resp.text
