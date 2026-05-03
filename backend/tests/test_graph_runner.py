import os
import unittest

from langgraph.types import Command, Send

from app.graph.state import GraphState
from app.graph.generate_subgraph import (
    GenerateSubState,
    build_generate_subgraph,
    prepare_prompt_node,
)
from app.graph.supervisor import route_supervisor, supervisor_node
from app.models.schemas import QualityScore, Stage, TrafficGenerateRequest, TrafficRecord
from app.services.graph_runner import build_initial_state, run_generation_graph


def _mock_record() -> TrafficRecord:
    """Minimal TrafficRecord for parallel dispatch tests."""
    from datetime import datetime, timezone
    return TrafficRecord(
        id="mock-001",
        method="GET",
        url="https://api.example.com/test",
        status_code=200,
        timestamp=datetime.now(timezone.utc),
        src_ip="192.168.1.1",
        src_port=8080,
        dst_ip="10.0.0.1",
        dst_port=443,
        header={},
        req_body={},
        resp_body={},
        rtt=50.0,
        duration=100.0,
        user_agent="Mozilla/5.0",
        referer="https://example.com",
        identity_label="real",
    )


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

    def test_supervisor_parallel_send_full_stage(self) -> None:
        """P2.3: Supervisor sets next_worker='__parallel__', route_supervisor returns Send[]."""
        import asyncio

        state: GraphState = {
            "session_id": "p23-test",
            "industry": "ecommerce",
            "stage": Stage.full,
            "count": 5,
            "scenario": "全天候配送",
            "retries": 0,
            "max_retries": 3,
            "retrieved_cases": [{"content": '{"method":"GET"}'}],
            "generated_records": [_mock_record()],
            "quality_score": QualityScore(
                format_score=0, business_score=0, diversity_score=0,
                total_score=0, passed=False,
            ),
            "quality_passed": False,
            "should_retry": False,
            "identity_checked": False,
            "error_message": "",
            "messages": [],
            "next_worker": "supervisor",
        }

        # 1. Supervisor node should return Command(goto="__parallel__")
        cmd = asyncio.run(supervisor_node(state))
        self.assertIsInstance(cmd, Command)
        self.assertEqual(cmd.goto, "__parallel__")
        self.assertEqual(cmd.update["next_worker"], "__parallel__")  # type: ignore[index]

        # 2. Simulate state after supervisor update for route_supervisor
        routed_state = {**state, **cmd.update}
        result = route_supervisor(routed_state)  # type: ignore[arg-type]

        self.assertIsInstance(result, list, "full stage should trigger parallel Send[]")
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], Send)
        self.assertIsInstance(result[1], Send)
        self.assertEqual(result[0].node, "eval")
        self.assertEqual(result[1].node, "identity")

    def test_supervisor_sequential_standard_stage(self) -> None:
        """P2.3: Standard stage remains sequential (no parallel dispatch)."""
        import asyncio

        from langgraph.types import Command

        state: GraphState = {
            "session_id": "p23-seq",
            "industry": "ride_hailing",
            "stage": Stage.standard,
            "count": 3,
            "scenario": "通勤高峰",
            "retries": 0,
            "max_retries": 3,
            "retrieved_cases": [{"content": '{"method":"POST"}'}],
            "generated_records": [_mock_record()],
            "quality_score": QualityScore(
                format_score=0, business_score=0, diversity_score=0,
                total_score=0, passed=False,
            ),
            "quality_passed": False,
            "should_retry": False,
            "identity_checked": False,
            "error_message": "",
            "messages": [],
            "next_worker": "supervisor",
        }

        result = asyncio.run(supervisor_node(state))

        # Standard stage should still use Command, not Send[]
        self.assertIsInstance(result, Command,
            f"standard stage should return Command, got {type(result).__name__}")

    def test_generate_subgraph_prompt_node(self) -> None:
        """P2.4: Subgraph prompt-preparation node populates prompt field."""
        import asyncio

        sub_state: GenerateSubState = {
            "industry": "ride_hailing",
            "scenario": "通勤高峰",
            "count": 5,
            "stage": Stage.standard,
            "prompt": "",
            "raw_response": "",
            "records": [],
            "error": "",
        }

        result = asyncio.run(prepare_prompt_node(sub_state))

        self.assertIn("prompt", result)
        prompt: str = result["prompt"]
        self.assertIn("ride_hailing", prompt)
        self.assertIn("通勤高峰", prompt)
        self.assertIn("5 条", prompt)
        self.assertIn("identity_label", prompt, "prompt should include field spec")

    def test_generate_subgraph_compiles(self) -> None:
        """P2.4: Subgraph compiles without error."""
        subgraph = build_generate_subgraph()
        self.assertIsNotNone(subgraph)
        # Verify the compiled graph has the expected nodes
        nodes = subgraph.get_graph().nodes
        node_names = {n for n in nodes.keys()}
        self.assertTrue(
            {"prepare_prompt", "call_llm", "parse_result"}.issubset(node_names),
            f"subgraph missing expected nodes, got: {node_names}",
        )

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
