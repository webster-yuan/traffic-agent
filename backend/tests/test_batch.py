import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import QualityScore, TrafficRecord
from datetime import datetime, timezone


class TestBatchRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def _quality(self) -> QualityScore:
        return QualityScore(
            format_score=90,
            business_score=88,
            diversity_score=87,
            total_score=88.3,
            passed=True,
        )

    def _rec(self, rid: str) -> TrafficRecord:
        return TrafficRecord(
            id=rid,
            method="GET",
            url="https://api.ecommerce.com/api/product/list",
            status_code=200,
            timestamp=datetime.now(timezone.utc),
            src_ip="192.168.1.100",
            src_port=54321,
            dst_ip="10.0.0.10",
            dst_port=443,
            header={"Content-Type": "application/json"},
            req_body=None,
            resp_body={"code": 0},
            rtt=100.0,
            duration=150.0,
            user_agent="Mozilla/5.0",
            referer="https://ecommerce.com",
            identity_label="real",
        )

    def test_batch_create_and_status(self) -> None:
        mock_tasks = [
            {
                "task_index": 0,
                "session_id": "abc123",
                "industry": "ecommerce",
                "stage": "quick",
                "count": 2,
                "status": "pending",
                "error_message": None,
            },
            {
                "task_index": 1,
                "session_id": "def456",
                "industry": "ride_hailing",
                "stage": "quick",
                "count": 2,
                "status": "pending",
                "error_message": None,
            },
        ]
        with patch(
            "app.api.routes.create_batch", AsyncMock(return_value=None)
        ), patch(
            "app.api.routes.add_batch_task", AsyncMock(return_value=None)
        ), patch(
            "app.api.routes.asyncio.create_task", lambda *a, **kw: None
        ), patch(
            "app.api.routes.get_batch_tasks", AsyncMock(return_value=mock_tasks)
        ):
            resp = self.client.post(
                "/api/v1/traffic/batch",
                json={
                    "tasks": [
                        {"industry": "ecommerce", "count": 2, "stage": "quick"},
                        {"industry": "ride_hailing", "count": 2, "stage": "quick"},
                    ]
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            batch_id = data["batch_id"]
            self.assertIsInstance(batch_id, str)
            self.assertEqual(len(batch_id), 8)

            status_resp = self.client.get(f"/api/v1/traffic/batch/{batch_id}")
            self.assertEqual(status_resp.status_code, 200)
            status_data = status_resp.json()
            self.assertEqual(status_data["batch_id"], batch_id)
            self.assertEqual(len(status_data["tasks"]), 2)
            self.assertFalse(status_data["finished"])

    def test_batch_all_completed(self) -> None:
        with patch(
            "app.api.routes.get_batch_tasks",
            AsyncMock(return_value=[
                {
                    "task_index": 0,
                    "session_id": "abc123",
                    "industry": "ecommerce",
                    "stage": "quick",
                    "count": 2,
                    "status": "completed",
                    "error_message": None,
                },
                {
                    "task_index": 1,
                    "session_id": "def456",
                    "industry": "ride_hailing",
                    "stage": "quick",
                    "count": 2,
                    "status": "completed",
                    "error_message": None,
                },
            ]),
        ):
            status_resp = self.client.get("/api/v1/traffic/batch/testbatch")
        self.assertEqual(status_resp.status_code, 200)
        status_data = status_resp.json()
        self.assertTrue(status_data["finished"])
        self.assertEqual(status_data["tasks"][0]["status"], "completed")
        self.assertEqual(status_data["tasks"][0]["progress"], 100)

    def test_batch_with_failed_task(self) -> None:
        with patch(
            "app.api.routes.get_batch_tasks",
            AsyncMock(return_value=[
                {
                    "task_index": 0,
                    "session_id": "abc123",
                    "industry": "ecommerce",
                    "stage": "quick",
                    "count": 2,
                    "status": "completed",
                    "error_message": None,
                },
                {
                    "task_index": 1,
                    "session_id": "def456",
                    "industry": "ride_hailing",
                    "stage": "quick",
                    "count": 2,
                    "status": "failed",
                    "error_message": "LLM timeout",
                },
            ]),
        ):
            status_resp = self.client.get("/api/v1/traffic/batch/testbatch")
        self.assertEqual(status_resp.status_code, 200)
        status_data = status_resp.json()
        self.assertTrue(status_data["finished"])
        self.assertEqual(status_data["tasks"][0]["status"], "completed")
        self.assertEqual(status_data["tasks"][1]["status"], "failed")
        self.assertEqual(status_data["tasks"][1]["error_message"], "LLM timeout")

    def test_batch_404_for_unknown_batch(self) -> None:
        with patch(
            "app.api.routes.get_batch_tasks", AsyncMock(return_value=[])
        ):
            status_resp = self.client.get("/api/v1/traffic/batch/unknown")
        self.assertEqual(status_resp.status_code, 404)

    def test_batch_empty_tasks_rejected(self) -> None:
        resp = self.client.post(
            "/api/v1/traffic/batch",
            json={"tasks": []},
        )
        self.assertEqual(resp.status_code, 422)

    def test_batch_too_many_tasks_rejected(self) -> None:
        tasks = [{"industry": "ecommerce", "count": 1, "stage": "quick"}] * 11
        resp = self.client.post(
            "/api/v1/traffic/batch",
            json={"tasks": tasks},
        )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
