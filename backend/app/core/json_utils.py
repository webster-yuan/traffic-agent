"""Shared JSON utilities used across services and graph nodes."""

import re


def fix_json(text: str) -> str:
    """Clean LLM output into valid JSON string.

    Handles markdown code fences, single-quote replacements,
    and trailing commas.
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty content")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text)
        text = text.strip("`")
    text = text.replace("'", '"')
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text
