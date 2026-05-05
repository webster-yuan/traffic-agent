"""Tests for app.tools.quality_eval — QualityEvalTool."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import QualityScore
from app.tools.quality_eval import QualityEvalTool


class TestQualityEvalTool:
    """Tests for QualityEvalTool — runs Pandera-based quality validation."""

    @pytest.fixture
    def tool(self) -> QualityEvalTool:
        return QualityEvalTool()

    def _mock_score(self, passed: bool = True) -> QualityScore:
        return QualityScore(
            format_score=90.0,
            business_score=85.0,
            diversity_score=80.0,
            total_score=85.0,
            passed=passed,
        )

    _VALID_RECORD = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "method": "GET",
        "url": "https://api.example.com/v1/users",
        "status_code": 200,
        "timestamp": "2025-01-01T00:00:00Z",
        "src_ip": "192.168.1.100",
        "src_port": 54321,
        "dst_ip": "10.0.0.1",
        "dst_port": 443,
        "header": {"Host": "api.example.com"},
        "req_body": None,
        "resp_body": {"data": []},
        "rtt": 45.0,
        "duration": 120.0,
        "user_agent": "Mozilla/5.0",
        "referer": None,
        "identity_label": "real",
    }

    # ── happy path ──────────────────────────────────────────────────

    def test_returns_quality_score_on_valid_records(self, tool):
        """QualityEvalTool returns a structured quality score for valid records."""
        score = self._mock_score(passed=True)
        with patch("app.tools.quality_eval.evaluate_quality", return_value=score):
            result = json.loads(tool._run(json.dumps([self._VALID_RECORD]), "ecommerce"))
        assert result["total_score"] == 85.0
        assert result["passed"] is True
        assert "format_score" in result

    def test_reports_failed_quality(self, tool):
        """QualityEvalTool correctly reports when quality check fails."""
        score = self._mock_score(passed=False)
        score.total_score = 45.0
        with patch("app.tools.quality_eval.evaluate_quality", return_value=score):
            result = json.loads(tool._run(json.dumps([self._VALID_RECORD]), "ecommerce"))
        assert result["passed"] is False
        assert result["total_score"] == 45.0

    def test_industry_is_passed_through(self, tool):
        """QualityEvalTool passes the industry key to evaluate_quality."""
        score = self._mock_score()
        with patch("app.tools.quality_eval.evaluate_quality") as mock_eval:
            mock_eval.return_value = score
            tool._run(json.dumps([self._VALID_RECORD]), "finance")
            mock_eval.assert_called_once()
            # second arg should be the industry string
            assert mock_eval.call_args[0][1] == "finance"

    # ── error handling ──────────────────────────────────────────────

    def test_returns_error_on_invalid_json(self, tool):
        """QualityEvalTool returns error dict when records_json is invalid."""
        result = json.loads(tool._run("not valid json", "ecommerce"))
        assert "error" in result

    def test_returns_error_on_invalid_record_fields(self, tool):
        """QualityEvalTool returns error when record fields don't match schema."""
        bad_record = {"id": "bad", "method": "INVALID_METHOD"}
        result = json.loads(tool._run(json.dumps([bad_record]), "ecommerce"))
        assert "error" in result

    # ── edge cases ──────────────────────────────────────────────────

    def test_empty_records_returns_score(self, tool):
        """QualityEvalTool handles empty record list gracefully."""
        score = self._mock_score()
        with patch("app.tools.quality_eval.evaluate_quality", return_value=score):
            result = json.loads(tool._run("[]", "ecommerce"))
        assert "total_score" in result

    def test_multiple_records(self, tool):
        """QualityEvalTool processes multiple records correctly."""
        records = [self._VALID_RECORD, self._VALID_RECORD, self._VALID_RECORD]
        score = self._mock_score()
        with patch("app.tools.quality_eval.evaluate_quality", return_value=score):
            result = json.loads(tool._run(json.dumps(records), "ecommerce"))
        assert result["passed"] is True
