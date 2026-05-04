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

    # ── Request identity ──
    session_id: str
    industry: str
    stage: Stage
    count: int

    # ── RAG context ──
    scenario: str
    retrieved_cases: list[dict]

    # ── Generation output ──
    generated_records: list[TrafficRecord]

    # ── Quality evaluation (4 fields) ──
    quality_score: QualityScore
    quality_passed: bool
    should_retry: bool
    eval_feedback: str  # aggregated failure notes from eval, fed back to generate

    # ── Human-in-the-Loop ──
    approval_action: str  # "approve" | "reject" | ""
    approval_hint: str    # user feedback when rejecting

    # ── Flow control ──
    retries: int
    max_retries: int
    identity_checked: bool
    error_message: str

    # ── Supervisor orchestration ──
    messages: Annotated[list[BaseMessage], operator.add]
    next_worker: str
