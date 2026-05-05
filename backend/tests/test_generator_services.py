"""Tests for app.services.generator — traffic generation utilities."""

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest

from app.models.schemas import QualityScore, Stage, TrafficRecord
from app.services.generator import (
    _get_examples,
    _get_llm_timeout,
    _random_body,
    _random_header,
    _random_ip,
    _random_port,
    _random_url,
    _score_diversity,
    evaluate_quality,
    generate_records,
    infer_scenario,
    write_csv,
    write_traffic_json,
)


class TestRandomHelpers:
    """Tests for random value generators."""

    def test_random_ip_format(self):
        """_random_ip returns a valid 192.168.x.x IP."""
        ip = _random_ip()
        parts = ip.split(".")
        assert len(parts) == 4
        assert parts[0] == "192"
        assert parts[1] == "168"
        assert 1 <= int(parts[2]) <= 255
        assert 1 <= int(parts[3]) <= 255

    def test_random_port_range(self):
        """_random_port returns a port in ephemeral range."""
        for _ in range(20):
            port = _random_port()
            assert 1024 <= port <= 65535

    def test_random_url_returns_valid_url(self):
        """_random_url returns a URL for a known industry."""
        url = _random_url("ecommerce")
        assert url.startswith("https://")
        assert "ecommerce" in url

    def test_random_url_falls_back_to_default(self):
        """_random_url returns default path for unknown industry."""
        url = _random_url("nonexistent_xyz")
        assert url.startswith("https://")
        assert "/api/endpoint" in url

    def test_random_header_script(self):
        """_random_header(is_script=True) returns script User-Agent."""
        header = _random_header(is_script=True)
        assert "User-Agent" in header
        ua = header["User-Agent"]
        script_tokens = ["python", "curl", "Go", "Scrapy", "Python", "urllib"]
        assert any(tok.lower() in ua.lower() for tok in script_tokens)

    def test_random_header_browser(self):
        """_random_header(is_script=False) returns browser User-Agent."""
        header = _random_header(is_script=False)
        assert "User-Agent" in header
        assert "Mozilla" in header["User-Agent"]


class TestGetLlmTimeout:
    """Tests for _get_llm_timeout()."""

    def test_returns_default_timeout(self):
        """_get_llm_timeout returns 300 by default."""
        timeout = _get_llm_timeout()
        assert timeout == 300


class TestScoreDiversity:
    """Tests for _score_diversity()."""

    def _make_record(self, **kwargs) -> TrafficRecord:
        defaults = {
            "id": "r1",
            "method": "GET",
            "url": "https://api.test.com/v1",
            "status_code": 200,
            "timestamp": datetime.now(timezone.utc),
            "src_ip": "192.168.1.1",
            "src_port": 12345,
            "dst_ip": "10.0.0.1",
            "dst_port": 443,
            "header": {},
            "req_body": None,
            "resp_body": None,
            "rtt": None,
            "duration": 100.0,
            "user_agent": "Mozilla/5.0",
            "referer": None,
            "identity_label": "real",
        }
        defaults.update(kwargs)
        return TrafficRecord(**defaults)

    def test_empty_records_returns_zero(self):
        """_score_diversity returns 0.0 for empty record list."""
        score, notes = _score_diversity([])
        assert score == 0.0
        assert "无记录可评" in notes

    def test_single_record_max_ratio(self):
        """_score_diversity: single record gets 100 since ratio=1.0 per category."""
        records = [self._make_record(id="r1")]
        score, notes = _score_diversity(records)
        # Ratio = len(unique)/min(count,expected) = 1/1 = 1.0 → full marks
        assert score == 100.0

    def test_diverse_records_score_high(self):
        """_score_diversity rewards varied URLs, methods, and statuses."""
        records = [
            self._make_record(id="r1", method="GET", url="https://a.com/1", status_code=200, identity_label="real"),
            self._make_record(id="r2", method="POST", url="https://a.com/2", status_code=201, identity_label="real"),
            self._make_record(id="r3", method="PUT", url="https://a.com/3", status_code=400, identity_label="fake"),
            self._make_record(id="r4", method="DELETE", url="https://a.com/4", status_code=500, identity_label="anomaly"),
        ]
        score, notes = _score_diversity(records)
        assert score >= 60


class TestEvaluateQuality:
    """Tests for evaluate_quality()."""

    def _make_record(self, **kwargs) -> TrafficRecord:
        defaults = {
            "id": "r1",
            "method": "GET",
            "url": "https://api.test.com/v1",
            "status_code": 200,
            "timestamp": datetime.now(timezone.utc),
            "src_ip": "192.168.1.1",
            "src_port": 12345,
            "dst_ip": "10.0.0.1",
            "dst_port": 443,
            "header": {},
            "req_body": None,
            "resp_body": None,
            "rtt": None,
            "duration": 100.0,
            "user_agent": "Mozilla/5.0",
            "referer": None,
            "identity_label": "real",
        }
        defaults.update(kwargs)
        return TrafficRecord(**defaults)

    def test_evaluate_quality_passes_high_scores(self):
        """evaluate_quality passes when all dimension scores are high."""
        records = [self._make_record()]
        with patch("app.services.generator._score_format", return_value=(90.0, [])):
            with patch("app.services.generator._score_business", return_value=(85.0, [])):
                with patch("app.services.generator._score_diversity", return_value=(80.0, [])):
                    result = evaluate_quality(records, "ecommerce")
        assert result.passed is True
        assert result.total_score >= 70

    def test_evaluate_quality_fails_low_scores(self):
        """evaluate_quality fails when scores are below threshold."""
        records = [self._make_record()]
        with patch("app.services.generator._score_format", return_value=(50.0, [])):
            with patch("app.services.generator._score_business", return_value=(40.0, [])):
                with patch("app.services.generator._score_diversity", return_value=(30.0, [])):
                    result = evaluate_quality(records, "ecommerce")
        assert result.passed is False
        assert result.total_score < 70

    def test_evaluate_quality_includes_notes(self):
        """evaluate_quality populates dimension notes."""
        records = [self._make_record()]
        with patch("app.services.generator._score_format", return_value=(90.0, ["good format"])):
            with patch("app.services.generator._score_business", return_value=(85.0, ["ok business"])):
                with patch("app.services.generator._score_diversity", return_value=(80.0, ["ok diversity"])):
                    result = evaluate_quality(records, "ecommerce")
        assert len(result.format_notes) > 0
        assert len(result.business_notes) > 0
        assert len(result.diversity_notes) > 0


class TestGenerateRecords:
    """Tests for generate_records() — non-LLM synthetic generation."""

    def test_generates_correct_count(self):
        """generate_records returns the requested number of records."""
        records = generate_records(count=5, stage=Stage.standard, industry="ecommerce")
        assert len(records) == 5
        assert all(isinstance(r, TrafficRecord) for r in records)

    def test_records_have_valid_fields(self):
        """generate_records produces records with valid field values."""
        records = generate_records(count=3, stage=Stage.standard, industry="finance")
        for r in records:
            assert r.method in ("GET", "POST", "PUT", "DELETE")
            assert r.url.startswith("https://")
            assert 100 <= r.status_code <= 599
            assert r.src_ip.startswith("192.168.")
            assert 1024 <= r.src_port <= 65535
            assert r.dst_ip.startswith("10.0.")
            assert r.dst_port in (80, 443, 8080, 8443)
            assert r.identity_label in ("real", "fake", "anomaly")

    def test_quick_stage_produces_anomaly(self):
        """generate_records with quick stage may include anomaly labels."""
        records = generate_records(count=20, stage=Stage.quick, industry="gaming")
        labels = {r.identity_label for r in records}
        assert "anomaly" in labels


class TestInferScenario:
    """Tests for infer_scenario()."""

    def test_returns_string_for_known_industry(self):
        """infer_scenario returns a scenario string for known industry."""
        scenario = infer_scenario("ecommerce")
        assert isinstance(scenario, str)
        assert len(scenario) > 0

    def test_returns_string_for_unknown_industry(self):
        """infer_scenario returns fallback for unknown industry."""
        scenario = infer_scenario("unknown_xyz")
        assert isinstance(scenario, str)


class TestGetExamples:
    """Tests for _get_examples()."""

    _SAMPLE = [{"id": "1", "method": "GET"}]

    def test_loads_industry_file(self):
        """_get_examples reads the industry-specific JSON file."""
        with patch("builtins.open", mock_open(read_data=json.dumps(self._SAMPLE))):
            with patch("pathlib.Path.exists", return_value=True):
                result = _get_examples("ecommerce")
        assert result == self._SAMPLE

    def test_falls_back_to_custom_when_missing(self):
        """_get_examples falls back to custom.json for unknown industries."""
        with patch("builtins.open", mock_open(read_data=json.dumps(self._SAMPLE))):
            with patch("pathlib.Path.exists", return_value=False):
                result = _get_examples("unknown_industry")
        assert result == self._SAMPLE


class TestWriteCsv:
    """Tests for write_csv()."""

    def _make_record(self, **kwargs) -> TrafficRecord:
        defaults = {
            "id": "r1",
            "method": "GET",
            "url": "https://api.test.com/v1",
            "status_code": 200,
            "timestamp": datetime.now(timezone.utc),
            "src_ip": "192.168.1.1",
            "src_port": 12345,
            "dst_ip": "10.0.0.1",
            "dst_port": 443,
            "header": {"Host": "test.com"},
            "req_body": None,
            "resp_body": {"ok": True},
            "rtt": 50.0,
            "duration": 120.0,
            "user_agent": "Mozilla/5.0",
            "referer": None,
            "identity_label": "real",
        }
        defaults.update(kwargs)
        return TrafficRecord(**defaults)

    def test_write_csv_creates_file(self, tmp_path, monkeypatch):
        """write_csv writes a CSV file and returns the path."""
        from app.core import config
        monkeypatch.setattr(config.settings, "output_dir", str(tmp_path))
        records = [self._make_record()]
        path = write_csv("sid001", records, "ecommerce")
        assert Path(path).exists()
        assert Path(path).suffix == ".csv"

    def test_write_csv_contains_headers(self, tmp_path, monkeypatch):
        """write_csv includes expected CSV headers."""
        from app.core import config
        monkeypatch.setattr(config.settings, "output_dir", str(tmp_path))
        records = [self._make_record()]
        path = write_csv("sid002", records, "finance")
        content = Path(path).read_text(encoding="utf-8")
        assert "id" in content
        assert "method" in content
        assert "url" in content

    def test_write_csv_handles_multiple_records(self, tmp_path, monkeypatch):
        """write_csv handles multiple records correctly."""
        from app.core import config
        monkeypatch.setattr(config.settings, "output_dir", str(tmp_path))
        records = [
            self._make_record(id="a", method="GET"),
            self._make_record(id="b", method="POST"),
        ]
        path = write_csv("sid003", records, "gaming")
        lines = Path(path).read_text(encoding="utf-8").strip().split("\n")
        # header + 2 records = 3 lines
        assert len(lines) == 3


class TestWriteTrafficJson:
    """Tests for write_traffic_json()."""

    def _make_record(self, **kwargs) -> TrafficRecord:
        defaults = {
            "id": "r1",
            "method": "GET",
            "url": "https://api.test.com/v1",
            "status_code": 200,
            "timestamp": datetime.now(timezone.utc),
            "src_ip": "192.168.1.1",
            "src_port": 12345,
            "dst_ip": "10.0.0.1",
            "dst_port": 443,
            "header": {},
            "req_body": None,
            "resp_body": None,
            "rtt": None,
            "duration": 100.0,
            "user_agent": "Mozilla/5.0",
            "referer": None,
            "identity_label": "real",
        }
        defaults.update(kwargs)
        return TrafficRecord(**defaults)

    def test_write_json_creates_file(self, tmp_path, monkeypatch):
        """write_traffic_json creates a valid JSON bundle."""
        from app.core import config
        monkeypatch.setattr(config.settings, "output_dir", str(tmp_path))
        records = [self._make_record()]
        quality = QualityScore(
            format_score=90, business_score=85, diversity_score=80,
            total_score=85, passed=True,
        )
        path = write_traffic_json(
            "sid001", records, "ecommerce",
            scenario="flash_sale", quality=quality, stage=Stage.standard,
        )
        assert Path(path).exists()
        assert Path(path).suffix == ".json"

    def test_write_json_includes_metadata(self, tmp_path, monkeypatch):
        """write_traffic_json JSON has metadata and records sections."""
        from app.core import config
        monkeypatch.setattr(config.settings, "output_dir", str(tmp_path))
        records = [self._make_record()]
        quality = QualityScore(
            format_score=90, business_score=85, diversity_score=80,
            total_score=85, passed=True,
        )
        path = write_traffic_json(
            "sid002", records, "ecommerce",
            scenario="test", quality=quality, stage=Stage.quick,
        )
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert "metadata" in data
        assert "records" in data
        assert data["metadata"]["session_id"] == "sid002"
        assert data["metadata"]["industry"] == "ecommerce"
