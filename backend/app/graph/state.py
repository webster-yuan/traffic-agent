import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage

from app.models.schemas import QualityScore, Stage, TrafficRecord


class GraphState(TypedDict):
    """Unified state for Supervisor-Worker agent graph.

    All original traffic-generation fields are preserved for backward
    compatibility.  The two new fields ``messages`` (accumulated conversation
    history) and ``next_worker`` (supervisor routing decision) enable the
    Supervisor → Worker orchestration pattern.
    """

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
    # --- Human-in-the-Loop approval fields ---
    approval_action: str  # "approve" | "reject" | ""
    approval_hint: str    # user feedback when rejecting
    # --- Prompt self-optimization feedback ---
    eval_feedback: str    # aggregated failure notes from eval, fed back to generate
    error_message: str
    # --- Supervisor-Worker orchestration fields ---
    messages: Annotated[list[BaseMessage], operator.add]
    next_worker: str
