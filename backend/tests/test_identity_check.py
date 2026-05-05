"""Tests for app.tools.identity_check — IdentityCheckTool."""

import json

import pytest

from app.tools.identity_check import IdentityCheckTool


class TestIdentityCheckTool:
    """Tests for IdentityCheckTool — validates identity_label on records."""

    @pytest.fixture
    def tool(self) -> IdentityCheckTool:
        return IdentityCheckTool()

    # ── happy path ──────────────────────────────────────────────────

    def test_real_records_pass(self, tool):
        """Real records with browser UAs pass identity check."""
        records = [
            {
                "id": "r1",
                "identity_label": "real",
                "user_agent": "Mozilla/5.0 Chrome/120",
                "status_code": 200,
            },
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["total"] == 1
        assert result["mismatches"] == 0
        assert result["passed"] == 1

    def test_fake_with_script_ua_passes(self, tool):
        """Fake-labeled records with script UA (python/curl/scrapy) pass."""
        for ua in ["python-requests/2.28", "curl/7.88", "go-http-client",
                    "Scrapy/2.9", "urllib/3.14", "httpx/0.25"]:
            records = [
                {
                    "id": "f1",
                    "identity_label": "fake",
                    "user_agent": ua,
                    "status_code": 200,
                },
            ]
            result = json.loads(tool._run(json.dumps(records)))
            assert result["mismatches"] == 0, f"UA '{ua}' should pass"

    def test_anomaly_with_5xx_passes(self, tool):
        """Anomaly-labeled records with 500+ status pass."""
        records = [
            {
                "id": "a1",
                "identity_label": "anomaly",
                "user_agent": "Mozilla/5.0",
                "status_code": 500,
            },
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["mismatches"] == 0

    def test_anomaly_with_high_rtt_passes(self, tool):
        """Anomaly records with rtt > 5000 pass."""
        records = [
            {
                "id": "a1",
                "identity_label": "anomaly",
                "user_agent": "Mozilla/5.0",
                "status_code": 200,
                "rtt": 6000,
            },
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["mismatches"] == 0

    def test_anomaly_with_high_duration_passes(self, tool):
        """Anomaly records with duration > 10000 pass."""
        records = [
            {
                "id": "a1",
                "identity_label": "anomaly",
                "user_agent": "Mozilla/5.0",
                "status_code": 200,
                "duration": 15000,
            },
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["mismatches"] == 0

    def test_anomaly_with_low_src_port_passes(self, tool):
        """Anomaly records with src_port < 1024 pass."""
        records = [
            {
                "id": "a1",
                "identity_label": "anomaly",
                "user_agent": "Mozilla/5.0",
                "status_code": 200,
                "src_port": 80,
            },
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["mismatches"] == 0

    # ── failure cases ───────────────────────────────────────────────

    def test_fake_without_script_ua_fails(self, tool):
        """Fake record with browser UA triggers mismatch."""
        records = [
            {
                "id": "f1",
                "identity_label": "fake",
                "user_agent": "Mozilla/5.0 Chrome/120",
                "status_code": 200,
            },
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["mismatches"] == 1
        assert result["details"][0]["issue"] == "fake label but no script UA"

    def test_anomaly_without_any_feature_fails(self, tool):
        """Anomaly record with no anomaly features triggers mismatch."""
        records = [
            {
                "id": "a1",
                "identity_label": "anomaly",
                "user_agent": "Mozilla/5.0",
                "status_code": 200,
                "src_port": 8080,
                "rtt": 100,
                "duration": 500,
            },
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["mismatches"] == 1

    def test_mixed_records(self, tool):
        """Mixed real/fake/anomaly records are checked independently."""
        records = [
            {"id": "r1", "identity_label": "real", "user_agent": "Mozilla/5.0", "status_code": 200},
            {"id": "f1", "identity_label": "fake", "user_agent": "python-requests", "status_code": 200},
            {"id": "a1", "identity_label": "anomaly", "user_agent": "Mozilla/5.0", "status_code": 500},
            {"id": "f2", "identity_label": "fake", "user_agent": "Mozilla/5.0", "status_code": 200},
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["total"] == 4
        assert result["mismatches"] == 1  # only f2 fails
        assert result["passed"] == 3

    # ── edge cases ──────────────────────────────────────────────────

    def test_empty_records(self, tool):
        """Empty record list returns zero totals."""
        result = json.loads(tool._run("[]"))
        assert result["total"] == 0
        assert result["mismatches"] == 0

    def test_invalid_json_returns_error(self, tool):
        """Malformed JSON input returns an error structure."""
        result = json.loads(tool._run("not json"))
        assert "error" in result

    def test_default_label_is_real(self, tool):
        """Records without identity_label default to 'real'."""
        records = [
            {"id": "r1", "user_agent": "Mozilla/5.0", "status_code": 200},
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert result["mismatches"] == 0

    def test_details_capped_at_20(self, tool):
        """details list is capped at 20 entries."""
        records = [
            {"id": f"f{i}", "identity_label": "fake", "user_agent": "Mozilla/5.0", "status_code": 200}
            for i in range(30)
        ]
        result = json.loads(tool._run(json.dumps(records)))
        assert len(result["details"]) == 20
