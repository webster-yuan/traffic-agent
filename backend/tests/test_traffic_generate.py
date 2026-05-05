"""Tests for app.tools.traffic_generate — TrafficGenerateTool."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.tools.traffic_generate import TrafficGenerateTool


class TestTrafficGenerateTool:
    """Tests for TrafficGenerateTool — generates traffic records via LLM."""

    @pytest.fixture
    def tool(self) -> TrafficGenerateTool:
        return TrafficGenerateTool()

    # ── _build_prompt ───────────────────────────────────────────────

    def test_build_prompt_includes_industry_and_scenario(self, tool):
        """_build_prompt embeds industry and scenario in the prompt."""
        prompt = tool._build_prompt("ecommerce", "flash_sale", 10, "[]")
        assert "ecommerce" in prompt
        assert "flash_sale" in prompt

    def test_build_prompt_includes_count(self, tool):
        """_build_prompt includes the target record count."""
        prompt = tool._build_prompt("gaming", "login", 50, "[]")
        assert "50" in prompt

    def test_build_prompt_includes_examples(self, tool):
        """_build_prompt includes the example JSON string."""
        examples = '[{"id": "1", "method": "GET"}]'
        prompt = tool._build_prompt("finance", "payment", 5, examples)
        assert examples in prompt

    def test_build_prompt_contains_format_requirements(self, tool):
        """_build_prompt contains output format requirements."""
        prompt = tool._build_prompt("media", "streaming", 10, "[]")
        assert "records" in prompt
        assert "JSON" in prompt

    # ── _run error handling ────────────────────────────────────────

    def test_run_returns_error_on_llm_failure(self, tool):
        """_run returns error dict when LLM is completely unavailable."""
        with patch("app.tools.traffic_generate._get_examples", return_value=[]):
            with patch("app.tools.traffic_generate.ChatOllama", side_effect=RuntimeError("no ollama")):
                result = json.loads(tool._run("ecommerce", "test", count=5))
        assert "error" in result

    def test_run_falls_back_to_raw_json_parse(self, tool):
        """_run falls back to raw JSON when structured output fails."""
        mock_llm = MagicMock()
        # First call (with_structured_output) raises
        mock_structured = MagicMock()
        mock_structured.invoke.side_effect = ValueError("structured failed")
        mock_llm.with_structured_output.return_value = mock_structured

        # Second call (raw invoke) returns a dict with records
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "records": [{"id": "r1", "method": "GET", "url": "https://x.com",
                         "status_code": 200, "timestamp": "2025-01-01T00:00:00Z",
                         "src_ip": "192.168.1.1", "src_port": 12345,
                         "dst_ip": "10.0.0.1", "dst_port": 443,
                         "header": {}, "req_body": None, "resp_body": None,
                         "rtt": 10.0, "duration": 100.0,
                         "user_agent": "Mozilla/5.0", "referer": None,
                         "identity_label": "real"}]
        })
        mock_llm.invoke.return_value = mock_response

        with patch("app.tools.traffic_generate._get_examples", return_value=[]):
            with patch("app.tools.traffic_generate.ChatOllama", return_value=mock_llm):
                result = json.loads(tool._run("ecommerce", "test", count=5))

        assert isinstance(result, list)
        assert len(result) > 0
