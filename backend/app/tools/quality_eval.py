"""Quality evaluation tool — runs Pandera-based validation on generated records."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.models.schemas import QualityScore
from app.services.generator import evaluate_quality

logger = logging.getLogger(__name__)


class QualityEvalInput(BaseModel):
    records_json: str = Field(description="JSON array string of traffic records to evaluate")
    industry: str = Field(description="Industry key for business-rule evaluation")


class QualityEvalTool(BaseTool):
    """Evaluate the quality of generated traffic records using Pandera schemas.

    Returns a structured quality report with format/business/diversity scores
    and detailed violation notes.
    """

    name: str = "quality_eval"
    description: str = (
        "Evaluate generated traffic records for format validity, business "
        "consistency, and diversity. Input is a JSON string of records and "
        "the industry key. Returns a quality score object with detailed notes."
    )
    args_schema: type[BaseModel] = QualityEvalInput

    def _run(self, records_json: str, industry: str) -> str:
        try:
            from app.models.schemas import TrafficRecord

            raw: list[dict[str, Any]] = json.loads(records_json)
            records: list[TrafficRecord] = []
            for item in raw:
                records.append(TrafficRecord(**item))
        except Exception as exc:
            logger.exception("QualityEvalTool: failed to parse records")
            return json.dumps({"error": f"Record parsing failed: {exc}"}, ensure_ascii=False)

        score: QualityScore = evaluate_quality(records, industry)
        return json.dumps(score.model_dump(), ensure_ascii=False)

    async def _arun(self, records_json: str, industry: str) -> str:
        return self._run(records_json=records_json, industry=industry)
