import unittest
from datetime import datetime, timezone

from app.models.schemas import TrafficRecord
from app.services.generator import evaluate_quality


def _record(**overrides) -> TrafficRecord:
    data = {
        "id": "record-001",
        "method": "POST",
        "url": "https://api.finance.com/api/payment/transfer",
        "status_code": 200,
        "timestamp": datetime.now(timezone.utc),
        "src_ip": "192.168.1.10",
        "src_port": 12345,
        "dst_ip": "10.0.0.10",
        "dst_port": 443,
        "header": {"Content-Type": "application/json"},
        "req_body": {"account_id": 100001, "amount": 88.8},
        "resp_body": {"code": 0},
        "rtt": 35.5,
        "duration": 120.0,
        "user_agent": "Mozilla/5.0",
        "referer": "https://finance.com/",
        "identity_label": "real",
    }
    data.update(overrides)
    return TrafficRecord(**data)


class TestQualityEvaluator(unittest.TestCase):
    def test_evaluate_quality_scores_valid_industry_records(self) -> None:
        records = [
            _record(id="record-001", method="POST", url="https://api.finance.com/api/payment/transfer"),
            _record(id="record-002", method="GET", url="https://api.finance.com/api/account/balance", req_body=None, status_code=201),
            _record(
                id="record-003",
                method="POST",
                url="https://api.finance.com/api/risk/check",
                user_agent="python-requests/2.28.0",
                identity_label="fake",
                status_code=400,
            ),
        ]

        quality = evaluate_quality(records, "finance")

        self.assertGreaterEqual(quality.format_score, 90)
        self.assertGreaterEqual(quality.business_score, 90)
        self.assertGreaterEqual(quality.diversity_score, 90)
        self.assertTrue(quality.passed)

    def test_evaluate_quality_penalizes_business_mismatch(self) -> None:
        records = [
            _record(url="https://api.unknown.com/api/test", method="GET", req_body={"unexpected": True}),
            _record(url="https://api.unknown.com/api/test", method="GET", req_body={"unexpected": True}),
        ]

        quality = evaluate_quality(records, "finance")

        self.assertLess(quality.business_score, 70)
        self.assertFalse(quality.passed)
        self.assertTrue(quality.business_notes)
        self.assertTrue(any("api.finance.com" in n for n in quality.business_notes))

    def test_evaluate_quality_populates_dimension_notes(self) -> None:
        records = [
            _record(id="record-001", method="POST", url="https://api.finance.com/api/payment/transfer"),
            _record(id="record-002", method="GET", url="https://api.finance.com/api/account/balance", req_body=None, status_code=201),
        ]
        quality = evaluate_quality(records, "finance")
        self.assertIsInstance(quality.format_notes, list)
        self.assertIsInstance(quality.business_notes, list)
        self.assertIsInstance(quality.diversity_notes, list)
        self.assertGreater(len(quality.diversity_notes), 0)

