import unittest

from app.models.schemas import Stage, TrafficGenerateRequest
from app.services.tracing_config import build_graph_config


class TestTracingConfig(unittest.TestCase):
    def test_build_graph_config_adds_langsmith_context(self) -> None:
        payload = TrafficGenerateRequest(
            industry="ride_hailing",
            count=12,
            stage=Stage.standard,
        )

        config = build_graph_config("sess_001", payload)

        self.assertEqual(config["configurable"]["thread_id"], "traffic_sess_001")
        self.assertEqual(config["run_name"], "traffic_generation")
        self.assertIn("traffic-agent", config["tags"])
        self.assertIn("ride_hailing", config["tags"])
        self.assertEqual(config["metadata"]["session_id"], "sess_001")
        self.assertEqual(config["metadata"]["stage"], "standard")
        self.assertEqual(config["metadata"]["source"], "frontend")
