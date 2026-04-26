import unittest

from app.models.schemas import Stage
from app.services.generator import generate_records, infer_scenario


class TestGeneratorIndustries(unittest.TestCase):
    def test_new_industries_have_scenarios(self) -> None:
        expected = {
            "finance": "交易高峰",
            "healthcare": "门诊就诊时段",
            "media": "晚间播放高峰",
            "social": "内容互动高峰",
            "gaming": "在线对战时段",
        }

        for industry, scenario in expected.items():
            with self.subTest(industry=industry):
                self.assertEqual(infer_scenario(industry), scenario)

    def test_fallback_generation_uses_industry_specific_urls(self) -> None:
        industries = ["finance", "healthcare", "media", "social", "gaming"]

        for industry in industries:
            with self.subTest(industry=industry):
                records = generate_records(3, Stage.standard, industry)

                self.assertEqual(len(records), 3)
                self.assertTrue(all(f"api.{industry}.com" in record.url for record in records))
                self.assertTrue(all(record.req_body is None or isinstance(record.req_body, dict) for record in records))

