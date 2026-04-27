"""Tests for JSON export bundle alongside CSV."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app.models.schemas import QualityScore, Stage, TrafficRecord
import pyarrow.parquet as pq

from app.services.generator import write_traffic_json, write_traffic_parquet


class TestExportJson(unittest.TestCase):
    def test_write_traffic_json_structure(self) -> None:
        rec = TrafficRecord(
            id="r1",
            method="GET",
            url="https://api.example.com/x",
            status_code=200,
            timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
            src_ip="10.0.0.1",
            src_port=1234,
            dst_ip="10.0.0.2",
            dst_port=443,
            header={},
            req_body=None,
            resp_body=None,
            rtt=1.0,
            duration=2.0,
            user_agent="ua",
            referer=None,
            identity_label="real",
        )
        quality = QualityScore(
            format_score=80.0,
            business_score=81.0,
            diversity_score=82.0,
            total_score=81.0,
            passed=True,
        )
        with TemporaryDirectory() as tmp:
            with patch(
                "app.services.generator.settings",
                SimpleNamespace(output_dir=tmp),
            ):
                path = write_traffic_json(
                    "sess1",
                    [rec],
                    "ecommerce",
                    scenario="场景",
                    quality=quality,
                    stage=Stage.standard,
                )
            self.assertTrue(path.endswith("traffic_ecommerce_sess1.json"))
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertIn("metadata", data)
        self.assertIn("records", data)
        self.assertEqual(data["metadata"]["session_id"], "sess1")
        self.assertEqual(data["metadata"]["industry"], "ecommerce")
        self.assertEqual(data["metadata"]["scenario"], "场景")
        self.assertEqual(data["metadata"]["stage"], "standard")
        self.assertEqual(data["metadata"]["total_records"], 1)
        self.assertEqual(data["metadata"]["quality"]["total_score"], 81.0)
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["id"], "r1")
        self.assertEqual(data["records"][0]["method"], "GET")


class TestExportParquet(unittest.TestCase):
    def test_write_traffic_parquet_readable(self) -> None:
        rec = TrafficRecord(
            id="r1",
            method="GET",
            url="https://api.ecommerce.com/api/cart/add",
            status_code=200,
            timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
            src_ip="10.0.0.1",
            src_port=1234,
            dst_ip="10.0.0.2",
            dst_port=443,
            header={"X": "1"},
            req_body=None,
            resp_body=None,
            rtt=1.0,
            duration=2.0,
            user_agent="ua",
            referer=None,
            identity_label="real",
        )
        with TemporaryDirectory() as tmp:
            with patch(
                "app.services.generator.settings",
                SimpleNamespace(output_dir=tmp),
            ):
                path = write_traffic_parquet("sess2", [rec], "ecommerce")
            self.assertTrue(path.endswith("traffic_ecommerce_sess2.parquet"))
            table = pq.read_table(path)
        self.assertEqual(table.num_rows, 1)
        self.assertEqual(table.column("id")[0].as_py(), "r1")
        self.assertEqual(table.column("method")[0].as_py(), "GET")
