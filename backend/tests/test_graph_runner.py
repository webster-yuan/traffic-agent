import os
import unittest

from app.models.schemas import Stage, TrafficGenerateRequest
from app.services.graph_runner import build_initial_state, run_generation_graph


class TestGraphRunner(unittest.TestCase):
    def test_build_initial_state_defaults(self) -> None:
        payload = TrafficGenerateRequest(
            industry="ride_hailing",
            count=12,
            stage=Stage.standard,
        )
        state = build_initial_state("sess_001", payload)

        self.assertEqual(state["session_id"], "sess_001")
        self.assertEqual(state["industry"], "ride_hailing")
        self.assertEqual(state["count"], 12)
        self.assertEqual(state["retries"], 0)
        self.assertEqual(state["max_retries"], 3)
        self.assertEqual(state["generated_records"], [])
        self.assertFalse(state["quality_passed"])

    def test_langsmith_tracing_enabled(self) -> None:
        self.assertTrue(os.environ.get("LANGCHAIN_TRACING_V2") == "true")
        self.assertIsNotNone(os.environ.get("LANGSMITH_API_KEY"))

    @unittest.skipIf(os.environ.get("OLLAMA_BASE_URL") is None, "OLLAMA not available")
    def test_graph_with_tracing(self) -> None:
        payload = TrafficGenerateRequest(
            industry="ecommerce",
            count=2,
            stage=Stage.quick,
        )
        result = run_generation_graph("test_tracing_001", payload)
        self.assertIn("generated_records", result)
        self.assertGreater(len(result["generated_records"]), 0)
