"""Route-level tests for observability endpoints: metrics, model-info, batch retry."""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


class TestMetricsEndpoint(unittest.TestCase):
    """GET /api/v1/traffic/metrics — system observability."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_metrics_returns_200(self) -> None:
        """Metrics endpoint returns HTTP 200."""
        resp = self.client.get("/api/v1/traffic/metrics")
        self.assertEqual(resp.status_code, 200)

    def test_metrics_has_required_keys(self) -> None:
        """Metrics response contains all expected top-level keys."""
        resp = self.client.get("/api/v1/traffic/metrics")
        data = resp.json()

        required_keys = [
            "uptime_seconds",
            "total_requests",
            "success_count",
            "failure_count",
            "success_rate",
            "total_records_generated",
            "throughput_rps",
            "latency_ms",
            "window_size",
            "token_usage",
            "concurrency",
        ]
        for key in required_keys:
            self.assertIn(
                key, data,
                f"Missing key '{key}' in metrics response: {list(data.keys())}",
            )

    def test_metrics_latency_structure(self) -> None:
        """Latency object contains P50/P95/P99/min/max/avg."""
        resp = self.client.get("/api/v1/traffic/metrics")
        latency = resp.json()["latency_ms"]

        for key in ["p50", "p95", "p99", "min", "max", "avg"]:
            self.assertIn(key, latency)

    def test_metrics_token_usage_structure(self) -> None:
        """Token usage contains expected fields."""
        resp = self.client.get("/api/v1/traffic/metrics")
        token_usage = resp.json()["token_usage"]

        for key in [
            "total_calls", "total_prompt_tokens", "total_completion_tokens",
            "total_tokens", "window_calls", "avg_tokens_per_call",
            "avg_completion_tokens_per_call", "avg_tokens_per_second",
            "avg_duration_ms",
        ]:
            self.assertIn(key, token_usage)

    def test_metrics_concurrency_info(self) -> None:
        """Concurrency information shows max_slots."""
        resp = self.client.get("/api/v1/traffic/metrics")
        concurrency = resp.json()["concurrency"]
        self.assertIn("max_slots", concurrency)
        self.assertEqual(concurrency["max_slots"], 3)

    def test_metrics_returns_valid_numbers(self) -> None:
        """All numeric fields are valid numbers (not NaN or None)."""
        resp = self.client.get("/api/v1/traffic/metrics")
        data = resp.json()

        self.assertGreaterEqual(data["success_rate"], 0)
        self.assertLessEqual(data["success_rate"], 1)
        self.assertIsInstance(data["throughput_rps"], (int, float))

        latency = data["latency_ms"]
        for val in latency.values():
            self.assertIsInstance(val, (int, float))


class TestModelInfoEndpoint(unittest.TestCase):
    """GET /api/v1/traffic/model-info — LLM configuration."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_model_info_returns_200(self) -> None:
        resp = self.client.get("/api/v1/traffic/model-info")
        self.assertEqual(resp.status_code, 200)

    def test_model_info_has_required_keys(self) -> None:
        resp = self.client.get("/api/v1/traffic/model-info")
        data = resp.json()

        required_keys = [
            "model", "base_url", "max_retries", "llm_timeout_seconds",
            "context_window_estimate", "capabilities", "supported_stages",
            "quality_dimensions", "quality_threshold",
        ]
        for key in required_keys:
            self.assertIn(key, data, f"Missing key '{key}' in model-info")

    def test_model_info_capabilities_is_list(self) -> None:
        resp = self.client.get("/api/v1/traffic/model-info")
        data = resp.json()
        self.assertIsInstance(data["capabilities"], list)
        self.assertGreater(len(data["capabilities"]), 0)

    def test_model_info_stages_is_list(self) -> None:
        resp = self.client.get("/api/v1/traffic/model-info")
        data = resp.json()
        self.assertIsInstance(data["supported_stages"], list)
        self.assertIn("full", data["supported_stages"])

    def test_model_info_quality_threshold(self) -> None:
        resp = self.client.get("/api/v1/traffic/model-info")
        data = resp.json()
        self.assertEqual(data["quality_threshold"], 70)

    def test_model_info_context_window(self) -> None:
        resp = self.client.get("/api/v1/traffic/model-info")
        data = resp.json()
        self.assertIsInstance(data["context_window_estimate"], int)
        self.assertGreater(data["context_window_estimate"], 0)


class TestBatchRetryEndpoint(unittest.TestCase):
    """POST /api/v1/traffic/batch/{batch_id}/retry-failed."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_retry_returns_404_for_unknown_batch(self) -> None:
        with patch("app.api.routes.get_batch_tasks", AsyncMock(return_value=[])):
            resp = self.client.post("/api/v1/traffic/batch/unknown/retry-failed")
        self.assertEqual(resp.status_code, 404)

    def test_retry_with_no_failed_tasks(self) -> None:
        mock_tasks = [
            {
                "task_index": 0,
                "session_id": "abc",
                "industry": "ecommerce",
                "stage": "quick",
                "count": 2,
                "status": "completed",
                "error_message": None,
            },
        ]
        with patch("app.api.routes.get_batch_tasks", AsyncMock(return_value=mock_tasks)):
            resp = self.client.post("/api/v1/traffic/batch/test/retry-failed")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["retried"], 0)

    def test_retry_with_failed_tasks(self) -> None:
        mock_tasks = [
            {
                "task_index": 0,
                "session_id": "abc",
                "industry": "ecommerce",
                "stage": "quick",
                "count": 2,
                "status": "failed",
                "error_message": "LLM timeout",
            },
            {
                "task_index": 1,
                "session_id": "def",
                "industry": "ride_hailing",
                "stage": "quick",
                "count": 2,
                "status": "completed",
                "error_message": None,
            },
        ]
        with (
            patch("app.api.routes.get_batch_tasks", AsyncMock(return_value=mock_tasks)),
            patch("app.api.routes.asyncio.create_task", lambda *args, **kwargs: None),
        ):
            resp = self.client.post("/api/v1/traffic/batch/test/retry-failed")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["retried"], 1)
        self.assertIn("1", data["message"])


if __name__ == "__main__":
    unittest.main()
