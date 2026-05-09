import tempfile
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

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
            "app.api.generate.run_graph",
            new_callable=AsyncMock,
        ) as mock_run_graph, patch("app.api.generate.write_csv", lambda *args, **kwargs: "tmp.csv"), patch(
            "app.api.generate.write_traffic_json", lambda *args, **kwargs: "tmp.json"
        ), patch(
            "app.api.generate.write_traffic_parquet", lambda *args, **kwargs: "tmp.parquet"
        ), patch(
            "app.api.generate.create_session", AsyncMock()
        ), patch(
            "app.api.generate.complete_session", AsyncMock()
        ), patch(
            "app.api.deps._acquire", AsyncMock()
        ):
            mock_run_graph.return_value = {
                "scenario": "通勤高峰",
                "quality_score": quality,
                "generated_records": [rec],
            }
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
            async def astream(self, *_args, **kwargs):
                # stream_mode=["updates", "custom"] — yield (mode, data) tuples
                _stream_mode = kwargs.get("stream_mode", [])
                emit_custom = "custom" in _stream_mode

                if emit_custom:
                    yield ("custom", {"type": "stage_start", "node": "rag", "name": "RAG检索", "message": "检索行业案例"})
                yield ("updates", {"rag": {"retries": 0}})

                if emit_custom:
                    yield ("custom", {"type": "stage_start", "node": "eval", "name": "质量评估", "message": "评估质量"})
                yield ("updates", {"eval": {
                    "retries": 1,
                    "scenario": "通勤高峰",
                    "quality_score": quality,
                    "generated_records": [rec],
                }})

        with patch("app.api.generate.get_traffic_graph", lambda: FakeGraph()), patch(
            "app.api.generate.write_csv", lambda *args, **kwargs: "tmp.csv"
        ), patch(
            "app.api.generate.write_traffic_json", lambda *args, **kwargs: "tmp.json"
        ), patch(
            "app.api.generate.write_traffic_parquet", lambda *args, **kwargs: "tmp.parquet"
        ), patch("app.api.generate.create_session", AsyncMock()), patch("app.api.deps._acquire", AsyncMock()):
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

    def test_download_json_serves_sidecar_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            csv_p = Path(d) / "traffic_x_abc123.csv"
            json_p = Path(d) / "traffic_x_abc123.json"
            csv_p.write_text("h\n", encoding="utf-8")
            json_p.write_text('{"metadata":{"ok":true}}', encoding="utf-8")
            with patch("app.api.history.get_session_file", AsyncMock(return_value=str(csv_p))):
                resp = self.client.get("/api/v1/traffic/download/abc123?format=json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["metadata"]["ok"])

    def test_download_json_404_when_sidecar_missing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            csv_p = Path(d) / "traffic_x_abc123.csv"
            csv_p.write_text("h\n", encoding="utf-8")
            with patch("app.api.history.get_session_file", AsyncMock(return_value=str(csv_p))):
                resp = self.client.get("/api/v1/traffic/download/abc123?format=json")
        self.assertEqual(resp.status_code, 404)

    def test_download_parquet_200(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            csv_p = Path(d) / "traffic_x_abc123.csv"
            pq_p = Path(d) / "traffic_x_abc123.parquet"
            csv_p.write_text("h\n", encoding="utf-8")
            pq_p.write_bytes(b"PAR1" + b"\x00" * 4)
            with patch("app.api.history.get_session_file", AsyncMock(return_value=str(csv_p))):
                resp = self.client.get("/api/v1/traffic/download/abc123?format=parquet")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(resp.headers.get("content-type", ""), ("application/vnd.apache.parquet",))

    def test_history_filtering_by_industry(self) -> None:
        """历史端点按行业筛选"""
        from app.models.schemas import SessionSummary, SessionStatus, Stage
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        mock_items = [
            SessionSummary(
                session_id="s1",
                industry="ecommerce",
                scenario="全天候配送",
                stage=Stage.standard,
                status=SessionStatus.completed,
                requested_count=3,
                record_count=3,
                quality_score=85.0,
                quality_detail=None,
                trace_thread_id=None,
                error_message=None,
                started_at=now,
                completed_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
        with patch("app.api.history.list_history", return_value=(1, mock_items)):
            resp = self.client.get(
                "/api/v1/traffic/history?page=1&page_size=20&industry=ecommerce"
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["industry"], "ecommerce")

    def test_history_filtering_by_status(self) -> None:
        """历史端点按状态筛选"""
        from app.models.schemas import SessionSummary, SessionStatus, Stage
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        mock_items = [
            SessionSummary(
                session_id="s2",
                industry="ride_hailing",
                scenario="通勤高峰",
                stage=Stage.quick,
                status=SessionStatus.failed,
                requested_count=5,
                record_count=0,
                quality_score=None,
                quality_detail=None,
                trace_thread_id=None,
                error_message="LLM timeout",
                started_at=now,
                completed_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
        with patch("app.api.history.list_history", return_value=(1, mock_items)):
            resp = self.client.get(
                "/api/v1/traffic/history?page=1&page_size=20&status=failed"
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["status"], "failed")

    def test_history_filtering_combined(self) -> None:
        """历史端点组合筛选"""
        with patch("app.api.history.list_history", return_value=(0, [])) as mock_fn:
            resp = self.client.get(
                "/api/v1/traffic/history?page=1&page_size=10&keyword=test&min_quality=70&date_from=2026-01-01"
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(len(data["items"]), 0)
        # 验证参数正确传递
        mock_fn.assert_called_once_with(
            1, 10,
            keyword="test",
            industry=None,
            stage=None,
            status=None,
            date_from="2026-01-01",
            date_to=None,
            min_quality=70.0,
        )

    def test_download_parquet_404(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            csv_p = Path(d) / "traffic_x_abc123.csv"
            csv_p.write_text("h\n", encoding="utf-8")
            with patch("app.api.history.get_session_file", AsyncMock(return_value=str(csv_p))):
                resp = self.client.get("/api/v1/traffic/download/abc123?format=parquet")
        self.assertEqual(resp.status_code, 404)

    # ---- Checkpoint Replay tests (P4.1) ----

    def test_list_checkpoints_returns_200(self) -> None:
        """GET /checkpoints/{session_id} returns empty list for non-existent session."""
        resp = self.client.get("/api/v1/traffic/checkpoints/nonexistent")
        # Even for non-existent sessions, the endpoint returns 200 with empty list
        # (LangGraph's aget_state_history yields nothing for unknown threads)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["session_id"], "nonexistent")
        self.assertIsInstance(data["checkpoints"], list)

    def test_replay_endpoint_with_mocked_replay(self) -> None:
        """POST /replay creates a new session from checkpoint."""
        rec = self._sample_record("id-replay")
        quality = QualityScore(
            format_score=92,
            business_score=91,
            diversity_score=89,
            total_score=90.7,
            passed=True,
        )
        with patch(
            "app.api.checkpoints.replay_from_checkpoint",
            new_callable=AsyncMock,
        ) as mock_replay, patch(
            "app.api.checkpoints.write_csv", lambda *args, **kwargs: "tmp.csv"
        ), patch(
            "app.api.checkpoints.write_traffic_json", lambda *args, **kwargs: "tmp.json"
        ), patch(
            "app.api.checkpoints.write_traffic_parquet", lambda *args, **kwargs: "tmp.parquet"
        ), patch(
            "app.api.checkpoints.create_session", AsyncMock()
        ), patch(
            "app.api.checkpoints.complete_session", AsyncMock()
        ), patch(
            "app.api.deps._acquire", AsyncMock()
        ):
            mock_replay.return_value = {
                "session_id": "replay123abc",
                "industry": "ride_hailing",
                "stage": "standard",
                "count": 3,
                "scenario": "通勤高峰",
                "quality_score": quality,
                "generated_records": [rec],
            }
            resp = self.client.post(
                "/api/v1/traffic/replay",
                json={
                    "session_id": "abc123",
                    "from_node": "rag",
                    "hint_override": "多生成POST请求",
                },
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["session_id"], "replay123abc")
        self.assertEqual(data["total_count"], 1)
        self.assertEqual(data["quality_score"]["total_score"], 90.7)

        # Verify replay_from_checkpoint was called with correct args
        mock_replay.assert_called_once_with(
            original_session_id="abc123",
            from_node="rag",
            hint_override="多生成POST请求",
        )

    def test_replay_without_hint_override(self) -> None:
        """POST /replay works without optional hint_override."""
        rec = self._sample_record("id-replay2")
        quality = QualityScore(
            format_score=90, business_score=90, diversity_score=90,
            total_score=90, passed=True,
        )
        with patch(
            "app.api.checkpoints.replay_from_checkpoint",
            new_callable=AsyncMock,
        ) as mock_replay, patch(
            "app.api.checkpoints.write_csv", lambda *args, **kwargs: "tmp.csv"
        ), patch(
            "app.api.checkpoints.write_traffic_json", lambda *args, **kwargs: "tmp.json"
        ), patch(
            "app.api.checkpoints.write_traffic_parquet", lambda *args, **kwargs: "tmp.parquet"
        ), patch(
            "app.api.checkpoints.create_session", AsyncMock()
        ), patch(
            "app.api.checkpoints.complete_session", AsyncMock()
        ), patch(
            "app.api.deps._acquire", AsyncMock()
        ):
            mock_replay.return_value = {
                "session_id": "replay456def",
                "industry": "ecommerce",
                "stage": "quick",
                "count": 5,
                "scenario": "全天候配送",
                "quality_score": quality,
                "generated_records": [rec],
            }
            resp = self.client.post(
                "/api/v1/traffic/replay",
                json={
                    "session_id": "def456",
                    "from_node": "generate",
                },
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        mock_replay.assert_called_once_with(
            original_session_id="def456",
            from_node="generate",
            hint_override=None,
        )
