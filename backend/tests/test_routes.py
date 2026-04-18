from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import QualityScore, TrafficRecord


class TestRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def _sample_record(self, rid: str) -> TrafficRecord:
        return TrafficRecord(
            id=rid,
            method="GET",
            url="https://api.example.com/test",
            status_code=200,
            timestamp=datetime.now(timezone.utc),
            src_ip="192.168.1.100",
            src_port=8080,
            dst_ip="10.0.0.1",
            dst_port=443,
            header={"Content-Type": "application/json"},
            req_body={"key": "value"},
            resp_body={"code": 0},
            rtt=120.5,
            duration=200.0,
            user_agent="Mozilla/5.0",
            referer="https://example.com",
            identity_label="real",
        )

    def test_generate_success_with_mocked_graph(self) -> None:
        rec = self._sample_record("id-1")
        quality = QualityScore(
            format_score=91,
            business_score=90,
            diversity_score=88,
            total_score=89.8,
            passed=True,
        )
        with patch(
            "app.api.routes.run_generation_graph",
            lambda session_id, payload: {
                "scenario": "通勤高峰",
                "quality_score": quality,
                "generated_records": [rec],
            },
        ), patch("app.api.routes.write_csv", lambda *args, **kwargs: "tmp.csv"), patch(
            "app.api.routes.create_session", lambda *args, **kwargs: None
        ):
            resp = self.client.post(
                "/api/v1/traffic/generate",
                json={"industry": "ride_hailing", "count": 1, "stage": "standard"},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_count"], 1)
        self.assertEqual(data["quality_score"]["total_score"], 89.8)

    def test_stream_emits_langgraph_stage_events(self) -> None:
        rec = self._sample_record("id-2")
        quality = QualityScore(
            format_score=90,
            business_score=89,
            diversity_score=87,
            total_score=88.7,
            passed=True,
        )

        class FakeGraph:
            async def astream_events(self, *_args, **_kwargs):
                yield {
                    "event": "on_chain_start",
                    "metadata": {"langgraph_node": "rag"},
                    "data": {},
                }
                yield {
                    "event": "on_chain_end",
                    "metadata": {"langgraph_node": "rag"},
                    "data": {"output": {"retries": 0}},
                }
                yield {
                    "event": "on_chain_end",
                    "metadata": {"langgraph_node": "eval"},
                    "data": {
                        "output": {
                            "retries": 1,
                            "scenario": "通勤高峰",
                            "quality_score": quality,
                            "generated_records": [rec],
                        }
                    },
                }

        with patch("app.api.routes.get_traffic_graph", lambda: FakeGraph()), patch(
            "app.api.routes.write_csv", lambda *args, **kwargs: "tmp.csv"
        ), patch("app.api.routes.create_session", lambda *args, **kwargs: None):
            resp = self.client.post(
                "/api/v1/traffic/generate/stream",
                json={"industry": "ride_hailing", "count": 1, "stage": "standard"},
            )
        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertIn("event: stage_start", text)
        self.assertIn("\"stage\":\"rag\"", text)
        self.assertIn("\"stage\":\"eval\"", text)
        self.assertIn("event: complete", text)
