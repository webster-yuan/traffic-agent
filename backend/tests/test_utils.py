"""Tests for app.core.utils — shared utility functions."""

from app.core.utils import dedupe_notes


class TestDedupeNotes:
    """Tests for dedupe_notes() — deduplicate & trim quality notes."""

    # ── happy path ──────────────────────────────────────────────────

    def test_removes_duplicates(self):
        """dedupe_notes removes duplicate entries, keeping first occurrence."""
        result = dedupe_notes(["low diversity", "low diversity", "bad format"])
        assert result == ["low diversity", "bad format"]

    def test_trims_whitespace(self):
        """dedupe_notes strips whitespace from each note."""
        result = dedupe_notes(["  good  ", "  bad  "])
        assert result == ["good", "bad"]

    def test_preserves_order(self):
        """dedupe_notes preserves the order of first occurrence."""
        result = dedupe_notes(["c", "a", "b", "a", "c"])
        assert result == ["c", "a", "b"]

    # ── edge cases ──────────────────────────────────────────────────

    def test_empty_list(self):
        """dedupe_notes returns empty list for empty input."""
        result = dedupe_notes([])
        assert result == []

    def test_empty_strings_are_filtered(self):
        """dedupe_notes ignores empty strings and whitespace-only notes."""
        result = dedupe_notes(["", "valid", "   ", "also valid"])
        assert result == ["valid", "also valid"]

    def test_all_duplicates_returns_single(self):
        """dedupe_notes returns one entry when all are the same."""
        result = dedupe_notes(["same", "same", "same"])
        assert result == ["same"]

    def test_default_cap_is_16(self):
        """dedupe_notes limits output to 16 entries by default."""
        notes = [f"note_{i}" for i in range(20)]
        result = dedupe_notes(notes)
        assert len(result) == 16
        assert result == [f"note_{i}" for i in range(16)]

    def test_custom_cap(self):
        """dedupe_notes respects a custom cap value."""
        notes = [f"note_{i}" for i in range(10)]
        result = dedupe_notes(notes, cap=3)
        assert len(result) == 3
        assert result == ["note_0", "note_1", "note_2"]

    def test_duplicates_count_toward_cap(self):
        """dedupe_notes doesn't double-count; cap applies to deduped result."""
        notes = ["a", "a", "b", "b", "c", "c", "d", "d"]
        result = dedupe_notes(notes, cap=2)
        assert len(result) == 2
        assert result == ["a", "b"]
