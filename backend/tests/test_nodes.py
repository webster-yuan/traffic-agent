import unittest
from datetime import datetime, timezone

from app.graph.generate_subgraph import summarize_generate_output
from app.models.schemas import Stage, TrafficRecord


class TestGraphNodes(unittest.TestCase):
    def test_summarize_generate_output_keeps_trace_payload_small(self) -> None:
        record = TrafficRecord(
            id="record-001",
            method="POST",
            url="https://api.ride_hailing.com/api/order/create",
            status_code=200,
            timestamp=datetime.now(timezone.utc),
            src_ip="192.168.1.10",
            src_port=12345,
            dst_ip="10.0.0.10",
            dst_port=443,
            header={"Content-Type": "application/json"},
            req_body={"order_id": "ORD001"},
            resp_body={"code": 0},
            rtt=88.8,
            duration=120.5,
            user_agent="python-requests/2.28.0",
            referer=None,
            identity_label="fake",
        )
        state = {
            "session_id": "sess_001",
            "industry": "ride_hailing",
            "scenario": "通勤高峰",
            "stage": Stage.quick,
            "count": 2,
            "retrieved_cases": [{"type": "llm_hint", "content": "按订单场景生成"}],
            "generated_records": [record],
        }

        summary = summarize_generate_output(state)

        self.assertEqual(summary["session_id"], "sess_001")
        self.assertEqual(summary["stage"], "quick")
        self.assertEqual(summary["requested_count"], 2)
        self.assertEqual(summary["generated_count"], 1)
        self.assertEqual(summary["identity_counts"], {"fake": 1})
        self.assertEqual(summary["sample_record"]["method"], "POST")
        self.assertEqual(summary["hint"], "按订单场景生成")

