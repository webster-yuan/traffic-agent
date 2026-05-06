"""In-memory system metrics for observability.

Tracks request counts, latencies, success/failure rates, and provides
P50/P95/P99 percentile calculations using a sliding window.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestSnapshot:
    """Single request timing record."""

    timestamp: float
    session_id: str
    industry: str
    stage: str
    record_count: int
    processing_time_ms: int
    success: bool
    error: str = ""


class SystemMetrics:
    """Thread-safe in-memory metrics tracker with percentile support."""

    def __init__(self, window_size: int = 500) -> None:
        self._lock = threading.Lock()
        self._window_size = window_size
        self._requests: list[RequestSnapshot] = []
        self._request_count: int = 0
        self._success_count: int = 0
        self._failure_count: int = 0
        self._total_records: int = 0
        self._start_time: float = time.time()

    def record_request(
        self,
        session_id: str,
        industry: str,
        stage: str,
        record_count: int,
        processing_time_ms: int,
        success: bool,
        error: str = "",
    ) -> None:
        """Record a completed request."""
        snap = RequestSnapshot(
            timestamp=time.time(),
            session_id=session_id,
            industry=industry,
            stage=stage,
            record_count=record_count,
            processing_time_ms=processing_time_ms,
            success=success,
            error=error,
        )
        with self._lock:
            self._requests.append(snap)
            # Trim to window_size
            if len(self._requests) > self._window_size:
                self._requests = self._requests[-self._window_size:]
            self._request_count += 1
            if success:
                self._success_count += 1
                self._total_records += record_count
            else:
                self._failure_count += 1

    @staticmethod
    def _percentile(sorted_values: list[float], pct: float) -> float:
        """Calculate percentile from sorted list."""
        if not sorted_values:
            return 0.0
        idx = (len(sorted_values) - 1) * pct
        lo = int(idx)
        hi = min(lo + 1, len(sorted_values) - 1)
        frac = idx - lo
        return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac

    def stats(self) -> dict[str, Any]:
        """Return comprehensive system metrics."""
        with self._lock:
            window = list(self._requests)
            uptime_seconds = time.time() - self._start_time
            total = self._request_count

            if not window:
                return {
                    "uptime_seconds": round(uptime_seconds, 1),
                    "total_requests": total,
                    "success_count": self._success_count,
                    "failure_count": self._failure_count,
                    "success_rate": 1.0 if total == 0 else round(self._success_count / max(total, 1), 4),
                    "total_records_generated": self._total_records,
                    "throughput_rps": 0.0,
                    "latency_ms": {
                        "p50": 0, "p95": 0, "p99": 0,
                        "min": 0, "max": 0, "avg": 0,
                    },
                    "window_size": 0,
                }

            latencies = sorted([r.processing_time_ms for r in window])
            success_window = [r for r in window if r.success]
            success_latencies = sorted([r.processing_time_ms for r in success_window]) if success_window else latencies

            # Throughput: requests per second over window
            if len(window) >= 2:
                window_duration = window[-1].timestamp - window[0].timestamp
                throughput = len(success_window) / max(window_duration, 0.001)
            else:
                throughput = total / max(uptime_seconds, 0.001)

            return {
                "uptime_seconds": round(uptime_seconds, 1),
                "total_requests": total,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "success_rate": round(self._success_count / max(total, 1), 4),
                "total_records_generated": self._total_records,
                "throughput_rps": round(throughput, 3),
                "latency_ms": {
                    "p50": round(self._percentile(success_latencies, 0.50), 1),
                    "p95": round(self._percentile(success_latencies, 0.95), 1),
                    "p99": round(self._percentile(success_latencies, 0.99), 1),
                    "min": min(latencies),
                    "max": max(latencies),
                    "avg": round(sum(latencies) / len(latencies), 1),
                },
                "window_size": len(window),
            }


# ── Singleton ──
_metrics: SystemMetrics | None = None


def get_metrics() -> SystemMetrics:
    """Return the global SystemMetrics singleton."""
    global _metrics
    if _metrics is None:
        _metrics = SystemMetrics()
    return _metrics
