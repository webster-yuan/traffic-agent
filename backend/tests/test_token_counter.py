"""Unit tests for token_counter.py — token usage tracking and extraction."""

import threading
from unittest.mock import MagicMock

import pytest

from app.services.token_counter import (
    TokenCounter,
    TokenSnapshot,
    extract_from_response,
    get_token_counter,
    record_llm_call,
)


class TestExtractFromResponse:
    """Token extraction from LangChain AIMessage / Ollama response metadata."""

    def test_extracts_from_response_metadata(self) -> None:
        """Extract token counts from response_metadata (Ollama fields)."""
        mock_response = MagicMock()
        mock_response.response_metadata = {
            "prompt_eval_count": 150,
            "eval_count": 80,
            "total_duration": 1_200_000_000,  # 1.2s in ns
        }
        mock_response.usage_metadata = {}

        result = extract_from_response(mock_response)
        assert result["prompt_tokens"] == 150
        assert result["completion_tokens"] == 80
        assert result["total_duration_ns"] == 1_200_000_000

    def test_extracts_from_usage_metadata(self) -> None:
        """Extract token counts from usage_metadata (LangChain standard)."""
        mock_response = MagicMock()
        mock_response.response_metadata = {}
        mock_response.usage_metadata = {
            "input_tokens": 200,
            "output_tokens": 100,
        }

        result = extract_from_response(mock_response)
        assert result["prompt_tokens"] == 200
        assert result["completion_tokens"] == 100
        assert result["total_duration_ns"] == 0

    def test_usage_metadata_takes_priority(self) -> None:
        """usage_metadata takes priority over response_metadata."""
        mock_response = MagicMock()
        mock_response.response_metadata = {
            "prompt_eval_count": 50,
            "eval_count": 30,
        }
        mock_response.usage_metadata = {
            "input_tokens": 200,
            "output_tokens": 100,
        }

        result = extract_from_response(mock_response)
        assert result["prompt_tokens"] == 200
        assert result["completion_tokens"] == 100

    def test_no_metadata_returns_zeros(self) -> None:
        """When no metadata is present, return zeros."""
        mock_response = MagicMock()
        mock_response.response_metadata = None
        mock_response.usage_metadata = None

        result = extract_from_response(mock_response)
        assert result["prompt_tokens"] == 0
        assert result["completion_tokens"] == 0
        assert result["total_duration_ns"] == 0

    def test_empty_metadata_returns_zeros(self) -> None:
        """Empty metadata dicts return zeros."""
        mock_response = MagicMock()
        mock_response.response_metadata = {}
        mock_response.usage_metadata = {}

        result = extract_from_response(mock_response)
        assert result["prompt_tokens"] == 0
        assert result["completion_tokens"] == 0


class TestTokenCounter:
    """TokenCounter accumulator and stats."""

    def test_empty_counter_returns_zero_stats(self) -> None:
        """Stats on empty counter return zeros."""
        counter = TokenCounter()
        stats = counter.stats()

        assert stats["total_calls"] == 0
        assert stats["total_tokens"] == 0
        assert stats["window_calls"] == 0
        assert stats["avg_tokens_per_call"] == 0
        assert stats["avg_duration_ms"] == 0.0

    def test_single_record_updates_stats(self) -> None:
        """Recording one call updates stats correctly."""
        counter = TokenCounter()
        counter.record(
            prompt_tokens=100,
            completion_tokens=50,
            model="test-model",
            total_duration_ns=2_000_000_000,
        )

        stats = counter.stats()
        assert stats["total_calls"] == 1
        assert stats["total_prompt_tokens"] == 100
        assert stats["total_completion_tokens"] == 50
        assert stats["total_tokens"] == 150
        assert stats["window_calls"] == 1
        assert stats["avg_tokens_per_call"] == 150.0
        assert stats["avg_completion_tokens_per_call"] == 50.0
        assert stats["avg_duration_ms"] == 2000.0

    def test_multiple_records_accumulate(self) -> None:
        """Multiple records accumulate correctly."""
        counter = TokenCounter()
        counter.record(prompt_tokens=100, completion_tokens=50, total_duration_ns=1_000_000_000)
        counter.record(prompt_tokens=200, completion_tokens=100, total_duration_ns=2_000_000_000)

        stats = counter.stats()
        assert stats["total_calls"] == 2
        assert stats["total_prompt_tokens"] == 300
        assert stats["total_completion_tokens"] == 150
        assert stats["total_tokens"] == 450
        assert stats["window_calls"] == 2
        assert stats["avg_tokens_per_call"] == 225.0
        assert stats["avg_completion_tokens_per_call"] == 75.0
        assert stats["avg_duration_ms"] == 1500.0

    def test_tokens_per_second_calculation(self) -> None:
        """avg_tokens_per_second is computed from completion tokens / duration."""
        counter = TokenCounter()
        # 50 tokens in 1 second = 50 t/s
        counter.record(prompt_tokens=10, completion_tokens=50, total_duration_ns=1_000_000_000)

        stats = counter.stats()
        assert stats["avg_tokens_per_second"] == 50.0

    def test_window_slides_old_records(self) -> None:
        """Old records are evicted from the sliding window (max 200)."""
        counter = TokenCounter()
        # Record 300 calls
        for i in range(300):
            counter.record(prompt_tokens=i, completion_tokens=1, total_duration_ns=1_000_000_000)

        stats = counter.stats()
        assert stats["total_calls"] == 300
        assert stats["window_calls"] == 200  # capped at _MAX_WINDOW

    def test_thread_safety(self) -> None:
        """Concurrent records from multiple threads don't corrupt state."""
        counter = TokenCounter()
        errors: list[Exception] = []

        def record_batch() -> None:
            try:
                for _ in range(50):
                    counter.record(prompt_tokens=10, completion_tokens=5, total_duration_ns=500_000_000)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_batch) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        stats = counter.stats()
        assert stats["total_calls"] == 500
        assert stats["total_tokens"] == 500 * 15

    def test_zero_duration_handled(self) -> None:
        """Zero duration doesn't cause divide-by-zero in t/s calculation."""
        counter = TokenCounter()
        counter.record(prompt_tokens=10, completion_tokens=10, total_duration_ns=0)

        stats = counter.stats()
        # Should not raise, fall back to 0 or reasonable value
        assert stats["avg_tokens_per_second"] >= 0


class TestTokenSnapshot:
    """TokenSnapshot dataclass properties."""

    def test_duration_ms_conversion(self) -> None:
        snap = TokenSnapshot(
            timestamp=0.0,
            model="test",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            total_duration_ns=1_500_000_000,
        )
        assert snap.duration_ms == 1500.0

    def test_tokens_per_second(self) -> None:
        snap = TokenSnapshot(
            timestamp=0.0,
            model="test",
            prompt_tokens=10,
            completion_tokens=100,
            total_tokens=110,
            total_duration_ns=2_000_000_000,
        )
        assert snap.tokens_per_second == 50.0

    def test_tokens_per_second_zero_duration(self) -> None:
        snap = TokenSnapshot(
            timestamp=0.0,
            model="test",
            prompt_tokens=10,
            completion_tokens=100,
            total_tokens=110,
            total_duration_ns=0,
        )
        assert snap.tokens_per_second == 0.0


class TestGlobalFunctions:
    """Global singleton and convenience functions."""

    def test_get_token_counter_returns_same_instance(self) -> None:
        """get_token_counter returns the same singleton."""
        c1 = get_token_counter()
        c2 = get_token_counter()
        assert c1 is c2

    def test_record_llm_call_with_tokens(self) -> None:
        """record_llm_call extracts tokens and records to global counter."""
        # Reset singleton for clean test
        import app.services.token_counter as mod
        mod._token_counter = TokenCounter()

        mock_response = MagicMock()
        mock_response.response_metadata = {
            "prompt_eval_count": 100,
            "eval_count": 50,
            "total_duration": 1_000_000_000,
        }
        mock_response.usage_metadata = {}

        record_llm_call(mock_response, model="test-model")
        stats = mod._token_counter.stats()

        assert stats["total_calls"] == 1
        assert stats["total_prompt_tokens"] == 100
        assert stats["total_completion_tokens"] == 50

    def test_record_llm_call_without_tokens(self) -> None:
        """record_llm_call with no tokens doesn't record anything."""
        import app.services.token_counter as mod
        mod._token_counter = TokenCounter()

        mock_response = MagicMock()
        mock_response.response_metadata = {}
        mock_response.usage_metadata = {}

        record_llm_call(mock_response)
        stats = mod._token_counter.stats()

        # No tokens = no record
        assert stats["total_calls"] == 0
