"""Tests for app.tools.rag_search — RAGSearchTool."""

import json
from unittest.mock import mock_open, patch

import pytest

from app.tools.rag_search import RAGSearchTool


class TestRAGSearchTool:
    """Tests for RAGSearchTool — searches industry traffic examples."""

    @pytest.fixture
    def tool(self) -> RAGSearchTool:
        return RAGSearchTool()

    _SAMPLE_EXAMPLES = [{"id": "1", "method": "GET"}, {"id": "2", "method": "POST"}]

    # ── happy path ──────────────────────────────────────────────────

    def test_returns_subset_with_limit(self, tool):
        """RAGSearchTool returns examples capped at the limit."""
        examples = [{"id": str(i)} for i in range(10)]
        with patch("builtins.open", mock_open(read_data=json.dumps(examples))):
            with patch("pathlib.Path.exists", return_value=True):
                result = json.loads(tool._run("ecommerce", limit=3))
        assert len(result) == 3

    def test_returns_full_list_when_fewer_than_limit(self, tool):
        """RAGSearchTool returns all examples when fewer than limit."""
        with patch("builtins.open", mock_open(read_data=json.dumps(self._SAMPLE_EXAMPLES))):
            with patch("pathlib.Path.exists", return_value=True):
                result = json.loads(tool._run("ecommerce", limit=10))
        assert len(result) == 2

    def test_preserves_example_structure(self, tool):
        """RAGSearchTool preserves the structure of example records."""
        with patch("builtins.open", mock_open(read_data=json.dumps(self._SAMPLE_EXAMPLES))):
            with patch("pathlib.Path.exists", return_value=True):
                result = json.loads(tool._run("ecommerce", limit=5))
        assert result[0]["id"] == "1"
        assert result[0]["method"] == "GET"

    # ── fallback to custom.json ─────────────────────────────────────

    def test_falls_back_to_custom_when_industry_missing(self, tool):
        """RAGSearchTool falls back to custom.json for unknown industries."""
        with patch("builtins.open", mock_open(read_data=json.dumps(self._SAMPLE_EXAMPLES))):
            with patch("pathlib.Path.exists", return_value=False):
                result = json.loads(tool._run("unknown_industry", limit=5))
        assert len(result) == 2

    # ── error handling ──────────────────────────────────────────────

    def test_returns_error_on_read_failure(self, tool):
        """RAGSearchTool returns error dict when file can't be read."""
        with patch("builtins.open", side_effect=OSError("permission denied")):
            with patch("pathlib.Path.exists", return_value=True):
                result = json.loads(tool._run("ecommerce"))
        assert "error" in result

    # ── edge cases ──────────────────────────────────────────────────

    def test_default_limit_is_3(self, tool):
        """RAGSearchTool defaults to limit=3."""
        examples = [{"id": str(i)} for i in range(10)]
        with patch("builtins.open", mock_open(read_data=json.dumps(examples))):
            with patch("pathlib.Path.exists", return_value=True):
                result = json.loads(tool._run("ecommerce"))
        assert len(result) == 3

    def test_empty_examples_returns_empty_list(self, tool):
        """RAGSearchTool returns empty list when examples file is empty."""
        with patch("builtins.open", mock_open(read_data="[]")):
            with patch("pathlib.Path.exists", return_value=True):
                result = json.loads(tool._run("ecommerce"))
        assert result == []

    def test_scenario_is_accepted_but_unused_in_search(self, tool):
        """RAGSearchTool accepts scenario param without error."""
        with patch("builtins.open", mock_open(read_data=json.dumps(self._SAMPLE_EXAMPLES))):
            with patch("pathlib.Path.exists", return_value=True):
                result = json.loads(tool._run("ecommerce", scenario="flash_sale", limit=1))
        assert len(result) == 1
