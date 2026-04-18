from typing import TypedDict

from app.models.schemas import QualityScore, Stage, TrafficRecord


class GraphState(TypedDict):
    session_id: str
    industry: str
    stage: Stage
    count: int
    scenario: str
    retries: int
    max_retries: int
    retrieved_cases: list[dict]
    generated_records: list[TrafficRecord]
    quality_score: QualityScore
    quality_passed: bool
    should_retry: bool
    identity_checked: bool
    error_message: str
