import unittest

from app.data.industries import (
    INDUSTRIES,
    INDUSTRY_KEYS,
    get_industry_context,
    get_industry_paths,
    infer_scenario,
)
from app.models.schemas import Industry, Stage
from app.services.generator import generate_records


class TestGeneratorIndustries(unittest.TestCase):
    def test_all_industry_keys_have_config(self) -> None:
        """Every key in INDUSTRY_KEYS must have a corresponding IndustryConfig."""
        for key in INDUSTRY_KEYS:
            with self.subTest(industry=key):
                cfg = INDUSTRIES.get(key)
                self.assertIsNotNone(cfg, f"Missing IndustryConfig for key={key}")
                self.assertEqual(cfg.key, key)
                self.assertTrue(cfg.label, f"Missing label for {key}")
                self.assertTrue(cfg.scenario, f"Missing scenario for {key}")
                self.assertTrue(cfg.context, f"Missing context for {key}")
                self.assertTrue(cfg.api_paths, f"Missing api_paths for {key}")

    def test_industry_literal_sync_with_data_module(self) -> None:
        """Industry Literal type must stay aligned with INDUSTRY_KEYS."""
        # Industry is Literal[...] — extract args via typing.get_args
        import typing
        literal_keys = set(typing.get_args(Industry))
        data_keys = set(INDUSTRY_KEYS)
        self.assertEqual(
            literal_keys, data_keys,
            f"Industry Literal is out of sync with INDUSTRY_KEYS! "
            f"Literal-only: {literal_keys - data_keys}, "
            f"Data-only: {data_keys - literal_keys}"
        )

    def test_infer_scenario_from_centralized_data(self) -> None:
        for key in INDUSTRY_KEYS:
            with self.subTest(industry=key):
                expected = INDUSTRIES[key].scenario
                self.assertEqual(infer_scenario(key), expected)

    def test_industry_context_from_centralized_data(self) -> None:
        for key in INDUSTRY_KEYS:
            with self.subTest(industry=key):
                expected = INDUSTRIES[key].context
                self.assertEqual(get_industry_context(key), expected)

    def test_industry_paths_from_centralized_data(self) -> None:
        for key in INDUSTRY_KEYS:
            with self.subTest(industry=key):
                expected = INDUSTRIES[key].api_paths
                self.assertEqual(get_industry_paths(key), expected)

    def test_fallback_generation_uses_industry_specific_urls(self) -> None:
        industries = ["finance", "healthcare", "media", "social", "gaming"]

        for industry in industries:
            with self.subTest(industry=industry):
                records = generate_records(3, Stage.standard, industry)

                self.assertEqual(len(records), 3)
                self.assertTrue(all(f"api.{industry}.com" in record.url for record in records))
                self.assertTrue(all(record.req_body is None or isinstance(record.req_body, dict) for record in records))

