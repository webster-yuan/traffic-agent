import unittest
from datetime import datetime, timedelta, timezone

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
        self.assertGreaterEqual(quality.total_score, 90)
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

    # ─── 新增: 字段合法性检测 ──────────────────────────────────

    def test_ip_format_invalid_is_penalized(self) -> None:
        """源/目标 IP 格式非法应扣分并记录到 format_notes。"""
        records = [
            _record(id="r1", src_ip="999.999.999.999"),
            _record(id="r2", dst_ip="not-an-ip"),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertLess(quality.format_score, 95,
                        f"IP 格式非法应扣分，实际: {quality.format_score}")
        self.assertTrue(quality.format_notes)
        self.assertTrue(any("IP" in n for n in quality.format_notes),
                        f"format_notes 应包含 IP 相关提示: {quality.format_notes}")

    def test_port_range_invalid_is_penalized(self) -> None:
        """源端口不在 1024-65535 / 目标端口非标准服务端口应扣分。"""
        records = [
            _record(id="r1", src_port=80),
            _record(id="r2", dst_port=9999),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertLess(quality.format_score, 95,
                        f"端口范围非法应扣分，实际: {quality.format_score}")
        self.assertTrue(quality.format_notes)
        self.assertTrue(any("端口" in n for n in quality.format_notes),
                        f"format_notes 应包含端口相关提示: {quality.format_notes}")

    def test_timestamp_future_is_penalized(self) -> None:
        """未来时间戳应扣分。"""
        far_future = datetime.now(timezone.utc) + timedelta(days=365)
        records = [
            _record(id="r1", timestamp=far_future),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertLess(quality.format_score, 95,
                        f"未来时间戳应扣分，实际: {quality.format_score}")
        self.assertTrue(quality.format_notes)
        self.assertTrue(any("时间戳" in n for n in quality.format_notes),
                        f"format_notes 应包含时间戳相关提示: {quality.format_notes}")

    def test_valid_ip_port_timestamp_scores_high(self) -> None:
        """合法 IP/端口/时间戳不应被扣分。"""
        records = [
            _record(id="r1", src_ip="10.0.0.1", dst_ip="192.168.1.1", src_port=10240, dst_port=443),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertGreaterEqual(quality.format_score, 90,
                                f"合法记录 format_score 应 >= 90，实际: {quality.format_score}")

    # ─── 新增: 业务一致性检测 ──────────────────────────────────

    def test_post_without_body_is_penalized(self) -> None:
        """POST/PUT 缺少 req_body 应在 business_score 中扣分。"""
        records = [
            _record(id="r1", method="POST", req_body=None),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertLess(quality.business_score, 100)
        self.assertTrue(quality.business_notes)
        self.assertTrue(any("body" in n for n in quality.business_notes),
                        f"business_notes 应包含 body 相关提示: {quality.business_notes}")

    def test_put_with_body_passes(self) -> None:
        """PUT 携带 body 应通过一致性检测。"""
        records = [
            _record(id="r1", method="PUT", req_body={"key": "val"}),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertGreaterEqual(quality.business_score, 80)

    def test_delete_with_200_body_is_penalized(self) -> None:
        """DELETE 返回 200 且带 body 应在 business 中扣分。"""
        records = [
            _record(id="r1", method="DELETE", status_code=200, resp_body={"deleted": True}),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertLess(quality.business_score, 100)
        self.assertTrue(quality.business_notes)
        self.assertTrue(any("DELETE" in n for n in quality.business_notes),
                        f"business_notes 应包含 DELETE 相关提示: {quality.business_notes}")

    def test_delete_204_passes(self) -> None:
        """DELETE 返回 204(无内容) 应通过检测。"""
        records = [
            _record(id="r1", method="DELETE", status_code=204, resp_body=None),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertGreaterEqual(quality.business_score, 80)

    # ─── 新增: 异常标签准确性检测 ──────────────────────────────

    def test_anomaly_without_features_is_penalized(self) -> None:
        """标记为 anomaly 但完全正常的记录应扣分。"""
        records = [
            _record(
                id="r1", identity_label="anomaly",
                status_code=200, rtt=35.0, duration=100.0,
                src_port=12345, dst_port=443,
            ),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertLess(quality.business_score, 100)
        self.assertTrue(quality.business_notes)
        self.assertTrue(any("anomaly" in n for n in quality.business_notes),
                        f"business_notes 应包含 anomaly 相关提示: {quality.business_notes}")

    def test_anomaly_with_features_passes(self) -> None:
        """标记为 anomaly 且有异常特征(5xx)的记录应通过检测。"""
        records = [
            _record(
                id="r1", identity_label="anomaly",
                status_code=500, rtt=50.0, duration=200.0,
                src_port=12345, dst_port=443,
            ),
        ]
        quality = evaluate_quality(records, "finance")

        self.assertGreaterEqual(quality.business_score, 80,
                                f"带 5xx 的 anomaly 应通过检测，实际: {quality.business_score}")

