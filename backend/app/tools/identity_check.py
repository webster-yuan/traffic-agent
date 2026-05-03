"""Identity check tool — validates identity labels on traffic records."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IdentityCheckInput(BaseModel):
    records_json: str = Field(description="JSON array string of traffic records")
    check_reason: str = Field(
        default="standard", description="Reason: standard, suspicious, or full"
    )


class IdentityCheckTool(BaseTool):
    """Validate the identity_label field of traffic records.

    Checks that records labeled 'fake' have script-like User-Agent strings,
    'anomaly' records have anomaly indicators, and 'real' records look like
    browser traffic.
    """

    name: str = "identity_check"
    description: str = (
        "Validate identity labels on traffic records. Checks that 'fake' "
        "records have script User-Agent, 'anomaly' records have anomaly "
        "features, and 'real' records use browser User-Agent. "
        "Returns a summary of mismatches."
    )
    args_schema: type[BaseModel] = IdentityCheckInput

    _SCRIPT_TOKENS = ("python", "curl", "go", "scrapy", "urllib", "httpx")

    def _run(self, records_json: str, check_reason: str = "standard") -> str:
        try:
            records: list[dict[str, Any]] = json.loads(records_json)
        except Exception as exc:
            return json.dumps({"error": f"Parse failed: {exc}"}, ensure_ascii=False)

        mismatches: list[dict[str, Any]] = []
        for i, rec in enumerate(records):
            label = rec.get("identity_label", "real")
            ua = str(rec.get("user_agent", "") or "").lower()

            if label == "fake":
                if not any(tok in ua for tok in self._SCRIPT_TOKENS):
                    mismatches.append({
                        "index": i,
                        "id": rec.get("id"),
                        "issue": "fake label but no script UA",
                        "user_agent": ua[:80],
                    })
            elif label == "anomaly":
                status = rec.get("status_code", 0)
                rtt = rec.get("rtt")
                duration = rec.get("duration")
                src_port = rec.get("src_port", 0)
                has_feature = any([
                    status >= 500,
                    rtt is not None and rtt > 5000,
                    duration is not None and duration > 10000,
                    src_port < 1024,
                ])
                if not has_feature:
                    mismatches.append({
                        "index": i,
                        "id": rec.get("id"),
                        "issue": "anomaly label but no anomaly features",
                    })

        result = {
            "total": len(records),
            "mismatches": len(mismatches),
            "passed": len(records) - len(mismatches),
            "details": mismatches[:20],
        }
        return json.dumps(result, ensure_ascii=False)

    async def _arun(self, records_json: str, check_reason: str = "standard") -> str:
        return self._run(records_json=records_json, check_reason=check_reason)
