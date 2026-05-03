"""RAG search tool — retrieves industry-specific traffic examples."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_EXAMPLES_DIR = Path(__file__).parent.parent.parent / "data" / "examples"


class RAGSearchInput(BaseModel):
    industry: str = Field(description="Industry key, e.g. ecommerce, finance, gaming")
    scenario: str = Field(default="", description="Optional scenario description")
    limit: int = Field(default=3, ge=1, le=10, description="Max results")


class RAGSearchTool(BaseTool):
    """Search industry-specific traffic examples from local JSON knowledge base.

    Falls back to ``custom.json`` when an industry file is missing.
    """

    name: str = "rag_search"
    description: str = (
        "Search the traffic-example knowledge base for an industry. "
        "Returns real traffic samples (JSON) that the generation worker "
        "should use as few-shot examples. "
        "Input: industry (required), scenario (optional), limit (optional)."
    )
    args_schema: type[BaseModel] = RAGSearchInput

    def _run(self, industry: str, scenario: str = "", limit: int = 3) -> str:
        path = _EXAMPLES_DIR / f"{industry}.json"
        if not path.exists():
            logger.warning("RAGSearchTool: %s not found, fallback custom.json", industry)
            path = _EXAMPLES_DIR / "custom.json"
        try:
            with open(path, encoding="utf-8") as f:
                examples: list[dict[str, Any]] = json.load(f)
        except Exception:
            return json.dumps({"error": f"Failed to load examples for {industry}"}, ensure_ascii=False)
        subset = examples[:limit]
        return json.dumps(subset, ensure_ascii=False, indent=2)

    async def _arun(self, industry: str, scenario: str = "", limit: int = 3) -> str:
        return self._run(industry=industry, scenario=scenario, limit=limit)
