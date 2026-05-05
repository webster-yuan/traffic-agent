"""Tests for app.core.json_utils — JSON repair utilities."""

import pytest

from app.core.json_utils import fix_json


class TestFixJson:
    """Tests for fix_json() — cleans LLM output into valid JSON."""

    # ── happy path ──────────────────────────────────────────────────

    def test_strips_whitespace(self):
        """fix_json strips leading/trailing whitespace."""
        result = fix_json('  {"a": 1}  ')
        assert result == '{"a": 1}'

    def test_removes_markdown_json_fence(self):
        """fix_json strips ```json ... ``` fences, leaving inner JSON."""
        result = fix_json('```json\n{"a": 1}\n```')
        # fences are removed; inner content preserved
        assert '{"a": 1}' in result
        assert not result.startswith("```")
        assert "```" not in result

    def test_removes_markdown_generic_fence(self):
        """fix_json strips plain ``` ... ``` fences."""
        result = fix_json('```\n{"a": 1}\n```')
        assert '{"a": 1}' in result
        assert not result.startswith("```")
        assert "```" not in result

    def test_replaces_single_quotes(self):
        """fix_json converts single-quoted keys/values to double quotes."""
        result = fix_json("{'key': 'value'}")
        assert result == '{"key": "value"}'

    def test_removes_trailing_comma_in_object(self):
        """fix_json removes trailing commas before closing brace."""
        result = fix_json('{"a": 1,}')
        assert result == '{"a": 1}'

    def test_removes_trailing_comma_in_array(self):
        """fix_json removes trailing commas before closing bracket."""
        result = fix_json('[1, 2,]')
        assert result == '[1, 2]'

    def test_handles_complex_input(self):
        """fix_json cleans a realistic LLM output with multiple issues."""
        result = fix_json(
            "```json\n{'records': [{'id': '1', 'name': 'test'},]}\n```"
        )
        assert '"records"' in result
        assert '"id"' in result
        assert '"name"' in result
        # no trailing comma before ]
        assert ",]" not in result
        # backtick fences are removed
        assert "```" not in result

    # ── edge cases ──────────────────────────────────────────────────

    def test_empty_input_raises(self):
        """fix_json raises ValueError on empty or whitespace-only input."""
        with pytest.raises(ValueError, match="Empty content"):
            fix_json("")

    def test_whitespace_only_raises(self):
        """fix_json raises ValueError on whitespace-only input."""
        with pytest.raises(ValueError, match="Empty content"):
            fix_json("   ")

    def test_already_valid_json_passes_through(self):
        """fix_json does not alter already-valid JSON."""
        valid = '{"status": 200, "data": [1, 2, 3]}'
        result = fix_json(valid)
        assert result == valid
