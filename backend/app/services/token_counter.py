"""Token usage tracking for LLM calls.

Extracts token counts from ChatOllama response metadata and maintains
in-memory and persistent statistics for cost analysis and observability.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory sliding window for recent token usages (last 200 calls) ──
_MAX_WINDOW = 200


@dataclass
class TokenSnapshot:
    """Single LLM call token statistics."""

    timestamp: float
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_duration_ns: int = 0  # Ollama total_duration in nanoseconds

    @property
    def duration_ms(self) -> float:
        return self.total_duration_ns / 1_000_000

    @property
    def tokens_per_second(self) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return self.completion_tokens / (self.duration_ms / 1000)


class TokenCounter:
    """Thread-safe token usage accumulator and reporter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window: deque[TokenSnapshot] = deque(maxlen=_MAX_WINDOW)
        # Accumulators (lifetime)
        self._total_calls: int = 0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_duration_ns: int = 0

    def record(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "",
        total_duration_ns: int = 0,
    ) -> None:
        """Record a single LLM call's token usage."""
        snap = TokenSnapshot(
            timestamp=time.time(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            total_duration_ns=total_duration_ns,
        )
        with self._lock:
            self._window.append(snap)
            self._total_calls += 1
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens
            self._total_duration_ns += total_duration_ns

    def stats(self) -> dict[str, Any]:
        """Return aggregated token statistics."""
        with self._lock:
            calls = len(self._window)
            if calls == 0:
                return {
                    "total_calls": self._total_calls,
                    "total_prompt_tokens": self._total_prompt_tokens,
                    "total_completion_tokens": self._total_completion_tokens,
                    "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
                    "window_calls": 0,
                    "avg_tokens_per_call": 0,
                    "avg_completion_tokens_per_call": 0,
                    "avg_tokens_per_second": 0.0,
                    "avg_duration_ms": 0.0,
                }

            snapshots = list(self._window)
            total_tokens = sum(s.total_tokens for s in snapshots)
            total_completion = sum(s.completion_tokens for s in snapshots)
            total_dur = sum(s.total_duration_ns for s in snapshots)

            return {
                "total_calls": self._total_calls,
                "total_prompt_tokens": self._total_prompt_tokens,
                "total_completion_tokens": self._total_completion_tokens,
                "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
                "window_calls": calls,
                "avg_tokens_per_call": round(total_tokens / calls, 1),
                "avg_completion_tokens_per_call": round(total_completion / calls, 1),
                "avg_tokens_per_second": round(
                    sum(s.completion_tokens for s in snapshots)
                    / max(sum(s.duration_ms for s in snapshots) / 1000, 0.001),
                    1,
                ),
                "avg_duration_ms": round(total_dur / calls / 1_000_000, 1),
            }


# ── Singleton ──
_token_counter: TokenCounter | None = None


def get_token_counter() -> TokenCounter:
    """Return the global TokenCounter singleton."""
    global _token_counter
    if _token_counter is None:
        _token_counter = TokenCounter()
    return _token_counter


def extract_from_response(response: Any) -> dict[str, int]:
    """Extract token counts from a LangChain AIMessage response.

    ChatOllama attaches usage metadata in ``response_metadata``:
    - ``prompt_eval_count``: input tokens
    - ``eval_count``: output tokens
    - ``total_duration``: nanoseconds

    Returns a dict with ``prompt_tokens``, ``completion_tokens``,
    ``total_duration_ns``, or zeros if unavailable.
    """
    meta: dict = getattr(response, "response_metadata", None) or {}
    usage: dict = getattr(response, "usage_metadata", None) or {}

    prompt_tokens = (
        usage.get("input_tokens", 0)
        or meta.get("prompt_eval_count", 0)
    )
    completion_tokens = (
        usage.get("output_tokens", 0)
        or meta.get("eval_count", 0)
    )
    total_duration_ns = meta.get("total_duration", 0)

    return {
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_duration_ns": int(total_duration_ns),
    }


def record_llm_call(response: Any, model: str = "qwen2.5:7b") -> None:
    """Convenience: extract tokens from AIMessage and record to global counter."""
    info = extract_from_response(response)
    if info["prompt_tokens"] or info["completion_tokens"]:
        get_token_counter().record(
            prompt_tokens=info["prompt_tokens"],
            completion_tokens=info["completion_tokens"],
            model=model,
            total_duration_ns=info["total_duration_ns"],
        )
        logger.debug(
            "token record: prompt=%d completion=%d duration_ns=%d",
            info["prompt_tokens"],
            info["completion_tokens"],
            info["total_duration_ns"],
        )
