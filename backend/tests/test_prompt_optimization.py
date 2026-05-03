"""Tests for Prompt Self-Optimization Feedback Loop (P3.7).

Verifies that eval worker produces actionable feedback on quality failure
and that generate subgraph injects it into the LLM prompt for improvement.
"""

import asyncio
import unittest

from app.graph.generate_subgraph import GenerateSubState, prepare_prompt_node
from app.models.schemas import QualityScore


class TestPromptSelfOptimization(unittest.TestCase):
    """Unit tests for the eval→generate feedback loop."""

    # ── prepare_prompt_node feedback injection ────────────────────────

    def test_prompt_inject_feedback_when_present(self) -> None:
        """Feedback section appended to prompt when eval_feedback is non-empty."""
        state: GenerateSubState = {
            "industry": "finance",
            "scenario": "payment transfer",
            "count": 5,
            "eval_feedback": "● 格式问题: missing header field\n● 业务问题: wrong port range",
        }
        result = asyncio.run(prepare_prompt_node(state))
        prompt: str = result["prompt"]
        self.assertIn("上一轮质量反馈", prompt)
        self.assertIn("missing header field", prompt)
        self.assertIn("wrong port range", prompt)
        # Feedback should appear after the main requirements
        feedback_pos = prompt.index("上一轮质量反馈")
        requirements_pos = prompt.index("重要要求")
        self.assertGreater(feedback_pos, requirements_pos)

    def test_prompt_no_feedback_when_empty(self) -> None:
        """Prompt unchanged when eval_feedback is empty string."""
        state: GenerateSubState = {
            "industry": "finance",
            "scenario": "payment transfer",
            "count": 5,
            "eval_feedback": "",
        }
        result = asyncio.run(prepare_prompt_node(state))
        prompt: str = result["prompt"]
        self.assertNotIn("上一轮质量反馈", prompt)
        self.assertIn("重要要求", prompt)  # still has core structure

    def test_prompt_no_feedback_when_key_missing(self) -> None:
        """Prompt unchanged when eval_feedback key absent from state."""
        state: GenerateSubState = {
            "industry": "ecommerce",
            "scenario": "order placement",
            "count": 3,
        }
        result = asyncio.run(prepare_prompt_node(state))
        prompt: str = result["prompt"]
        self.assertNotIn("上一轮质量反馈", prompt)
        self.assertIn("重要要求", prompt)

    # ── QualityScore notes → feedback string logic ────────────────────

    def test_quality_score_builds_notes_on_failure(self) -> None:
        """QualityScore stores actionable notes in dimension fields on failure."""
        qs = QualityScore(
            format_score=60,
            business_score=50,
            diversity_score=40,
            total_score=51,
            passed=False,
            format_notes=["missing Content-Type header in 3 records"],
            business_notes=["port 80 used for payment API (should be 443)"],
            diversity_notes=["only GET requests, no POST/PUT"],
        )
        self.assertFalse(qs.passed)
        self.assertEqual(len(qs.format_notes), 1)
        self.assertEqual(len(qs.business_notes), 1)
        self.assertEqual(len(qs.diversity_notes), 1)

    def test_quality_passed_has_no_notes(self) -> None:
        """When quality passes, notes may be empty or informational."""
        qs = QualityScore(
            format_score=95,
            business_score=92,
            diversity_score=88,
            total_score=91,
            passed=True,
        )
        self.assertTrue(qs.passed)
        # Notes default to empty list
        self.assertEqual(qs.format_notes, [])
        self.assertEqual(qs.business_notes, [])
        self.assertEqual(qs.diversity_notes, [])


if __name__ == "__main__":
    unittest.main()
