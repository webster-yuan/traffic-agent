"""Unit tests for system_metrics.py — request latency and throughput tracking."""

import threading

import pytest

from app.services.system_metrics import (
    RequestSnapshot,
    SystemMetrics,
    get_metrics,
)


class TestRequestSnapshot:
    """RequestSnapshot dataclass."""

    def test_defaults(self) -> None:
        snap = RequestSnapshot(
            timestamp=1000.0,
            session_id="abc",
            industry="ecommerce",
            stage="standard",
            record_count=5,
            processing_time_ms=1500,
            success=True,
        )
        assert snap.session_id == "abc"
        assert snap.error == ""

    def test_error_field(self) -> None:
        snap = RequestSnapshot(
            timestamp=1000.0,
            session_id="abc",
            industry="ecommerce",
            stage="standard",
            record_count=0,
            processing_time_ms=30000,
            success=False,
            error="LLM timeout",
        )
        assert snap.error == "LLM timeout"
        assert not snap.success


class TestSystemMetricsEmpty:
    """Stats on unused counter."""

    def test_empty_metrics_returns_zero_stats(self) -> None:
        metrics = SystemMetrics()
        stats = metrics.stats()

        assert stats["total_requests"] == 0
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 1.0  # 0/0 → no failures yet
        assert stats["total_records_generated"] == 0
        assert stats["throughput_rps"] == 0.0
        assert stats["latency_ms"]["p50"] == 0
        assert stats["latency_ms"]["p95"] == 0
        assert stats["latency_ms"]["p99"] == 0
        assert stats["window_size"] == 0


class TestSystemMetricsSingle:
    """Single request tracking."""

    def test_single_success_records_correctly(self) -> None:
        metrics = SystemMetrics()
        metrics.record_request(
            session_id="s1",
            industry="ecommerce",
            stage="standard",
            record_count=10,
            processing_time_ms=5000,
            success=True,
        )

        stats = metrics.stats()
        assert stats["total_requests"] == 1
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["total_records_generated"] == 10
        assert stats["window_size"] == 1

    def test_single_failure_records_correctly(self) -> None:
        metrics = SystemMetrics()
        metrics.record_request(
            session_id="s1",
            industry="ecommerce",
            stage="standard",
            record_count=0,
            processing_time_ms=30000,
            success=False,
            error="timeout",
        )

        stats = metrics.stats()
        assert stats["total_requests"] == 1
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 1
        assert stats["success_rate"] == 0.0
        assert stats["total_records_generated"] == 0
        assert stats["window_size"] == 1


class TestSystemMetricsMultiple:
    """Multiple request tracking."""

    def test_multiple_requests_accumulate(self) -> None:
        metrics = SystemMetrics()
        for i in range(5):
            metrics.record_request(
                session_id=f"s{i}",
                industry="ecommerce",
                stage="standard",
                record_count=5,
                processing_time_ms=1000 + i * 100,
                success=True,
            )

        stats = metrics.stats()
        assert stats["total_requests"] == 5
        assert stats["success_count"] == 5
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["total_records_generated"] == 25
        assert stats["window_size"] == 5

    def test_mixed_success_failure(self) -> None:
        metrics = SystemMetrics()
        metrics.record_request(session_id="s1", industry="e", stage="s", record_count=5, processing_time_ms=1000, success=True)
        metrics.record_request(session_id="s2", industry="e", stage="s", record_count=0, processing_time_ms=2000, success=False)
        metrics.record_request(session_id="s3", industry="e", stage="s", record_count=5, processing_time_ms=3000, success=True)

        stats = metrics.stats()
        assert stats["total_requests"] == 3
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 1
        assert stats["success_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert stats["total_records_generated"] == 10


class TestPercentile:
    """P50/P95/P99 calculation."""

    def test_percentile_single_value(self) -> None:
        metrics = SystemMetrics()
        metrics.record_request(session_id="s", industry="e", stage="s", record_count=1, processing_time_ms=500, success=True)
        stats = metrics.stats()
        assert stats["latency_ms"]["p50"] == 500.0
        assert stats["latency_ms"]["p95"] == 500.0
        assert stats["latency_ms"]["p99"] == 500.0
        assert stats["latency_ms"]["min"] == 500
        assert stats["latency_ms"]["max"] == 500
        assert stats["latency_ms"]["avg"] == 500.0

    def test_percentile_multiple_values(self) -> None:
        metrics = SystemMetrics()
        for t in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]:
            metrics.record_request(session_id="s", industry="e", stage="s", record_count=1, processing_time_ms=t, success=True)

        stats = metrics.stats()
        # P50 of sorted [100..1000] with 10 items
        # idx = (10-1)*0.50 = 4.5 → lo=4(500), hi=5(600), frac=0.5 → 500+0.5*100=550
        assert stats["latency_ms"]["p50"] == 550.0
        assert stats["latency_ms"]["p95"] == pytest.approx(955.0, abs=1.0)
        assert stats["latency_ms"]["p99"] == pytest.approx(991.0, abs=1.0)
        assert stats["latency_ms"]["min"] == 100
        assert stats["latency_ms"]["max"] == 1000
        assert stats["latency_ms"]["avg"] == 550.0

    def test_latency_only_counts_success(self) -> None:
        """P50/P95/P99 only considers successful requests."""
        metrics = SystemMetrics()
        metrics.record_request(session_id="s1", industry="e", stage="s", record_count=1, processing_time_ms=100, success=True)
        metrics.record_request(session_id="s2", industry="e", stage="s", record_count=1, processing_time_ms=50000, success=False)
        metrics.record_request(session_id="s3", industry="e", stage="s", record_count=1, processing_time_ms=300, success=True)

        stats = metrics.stats()
        # Only successes [100, 300] used for percentile
        assert stats["latency_ms"]["p50"] == 200.0
        # min/max still from all
        assert stats["latency_ms"]["max"] == 50000


class TestWindowEviction:
    """Sliding window eviction."""

    def test_window_trims_old_records(self) -> None:
        metrics = SystemMetrics(window_size=10)
        for i in range(30):
            metrics.record_request(session_id=f"s{i}", industry="e", stage="s", record_count=1, processing_time_ms=i, success=True)

        stats = metrics.stats()
        assert stats["total_requests"] == 30  # lifetime total
        assert stats["window_size"] == 10  # capped
        # Window should have last 10 items (indices 20-29, values 20-29)
        assert stats["latency_ms"]["min"] == 20
        assert stats["latency_ms"]["max"] == 29


class TestThreadSafety:
    """Concurrent access."""

    def test_concurrent_records(self) -> None:
        metrics = SystemMetrics()
        errors: list[Exception] = []

        def record_batch() -> None:
            try:
                for i in range(25):
                    metrics.record_request(
                        session_id=f"s{i}",
                        industry="ecommerce",
                        stage="standard",
                        record_count=1,
                        processing_time_ms=i,
                        success=True,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_batch) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        stats = metrics.stats()
        assert stats["total_requests"] == 100


class TestSingleton:
    """Global singleton behavior."""

    def test_get_metrics_returns_same_instance(self) -> None:
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2


class TestThroughput:
    """Throughput RPS calculation."""

    def test_throughput_single_request(self) -> None:
        """Single request — throughput = 1 / uptime."""
        metrics = SystemMetrics()
        metrics.record_request(session_id="s", industry="e", stage="s", record_count=1, processing_time_ms=100, success=True)
        stats = metrics.stats()
        assert stats["throughput_rps"] > 0
