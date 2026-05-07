"""Worker agent nodes for the Supervisor-Worker graph.

Each worker is an async function that:
1. Reads relevant fields from AgentState
2. Executes its domain task (RAG / generate / eval / identity)
3. Returns ``Command(goto="supervisor", update={...})`` to resume orchestration
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command, interrupt

from app.core.state import is_cancelled
from app.graph.generate_subgraph import build_generate_subgraph
from app.graph.shared import check_cancelled as _check_cancelled
from app.graph.state import GraphState
from app.models.schemas import QualityScore, Stage, TrafficRecord
from app.services.generator import (
    _get_examples,
    evaluate_quality,
    infer_scenario,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RAG Worker
# ---------------------------------------------------------------------------

async def rag_worker(state: GraphState) -> Command[dict[str, Any]]:  # type: ignore[type-arg]
    """Retrieve industry-specific examples and infer scenario."""
    session_id: str = state.get("session_id", "")  # type: ignore[assignment]
    industry: str = state.get("industry", "")  # type: ignore[assignment]
    _check_cancelled(session_id)

    # ── Custom streaming: stage start ──────────────────────────────────
    try:
        writer = get_stream_writer()
        writer({
            "type": "stage_start",
            "node": "rag",
            "name": "RAG检索",
            "message": f"检索 {industry} 行业案例并推断场景",
        })
    except RuntimeError:
        pass

    logger.info("[RAG Worker] session=%s industry=%s", session_id, industry)
    scenario = infer_scenario(industry)
    examples = _get_examples(industry)

    retrieved = [
        {
            "industry": industry,
            "scenario": scenario,
            "content": json.dumps(e, ensure_ascii=False),
        }
        for e in examples[:5]
    ]

    msg = HumanMessage(
        content=f"RAG completed: industry={industry}, scenario={scenario}, loaded {len(retrieved)} examples",
        name="rag",
    )

    return Command(
        goto="supervisor",
        update={
            "scenario": scenario,
            "retrieved_cases": retrieved,
            "messages": [msg],
        },
    )


# ---------------------------------------------------------------------------
# Generate Worker
# ---------------------------------------------------------------------------

async def generate_worker(state: GraphState) -> Command[dict[str, Any]]:  # type: ignore[type-arg]
    """Generate traffic records via the nested generate subgraph (P2.4).

    The subgraph encapsulates prompt preparation, LLM invocation, and
    result parsing as an independently testable unit.
    """
    session_id: str = state.get("session_id", "")  # type: ignore[assignment]
    _check_cancelled(session_id)

    count: int = state.get("count", 10)  # type: ignore[assignment]

    # ââ Custom streaming: stage start ââââââââââââââââââââââââââ
    try:
        writer = get_stream_writer()
        writer({
            "type": "stage_start",
            "node": "generate",
            "name": "流量生成",
            "message": f"根据场景和案例调用 LLM 生成 {count} 条流量记录",
        })
    except RuntimeError:
        pass

    stage: Stage = state.get("stage", Stage.standard)  # type: ignore[assignment]
    industry: str = state.get("industry", "")  # type: ignore[assignment]
    scenario: str = state.get("scenario", "")  # type: ignore[assignment]

    logger.info("[Generate Worker] session=%s count=%d (via subgraph)", session_id, count)

    # Merge eval_feedback and approval_hint for self-optimization (I15)
    eval_feedback: str = state.get("eval_feedback", "")  # type: ignore[assignment]
    approval_hint: str = state.get("approval_hint", "")  # type: ignore[assignment]
    combined_feedback: str = eval_feedback
    if approval_hint:
        hint_line = f"● Human review feedback: {approval_hint}"
        combined_feedback = (
            f"{eval_feedback}\n{hint_line}" if eval_feedback else hint_line
        )

    # Build initial subgraph state from parent state
    sub_state = {
        "industry": industry,
        "scenario": scenario,
        "count": count,
        "stage": stage,
        "prompt": "",
        "raw_response": "",
        "records": [],
        "error": "",
        "eval_feedback": combined_feedback,  # P3.7 + I15: merged feedback
    }

    subgraph = build_generate_subgraph()
    result = await subgraph.ainvoke(sub_state)

    records: list[TrafficRecord] = result.get("records", []) or []
    error: str = result.get("error", "") or ""

    if error and not records:
        msg = HumanMessage(
            content=f"Traffic generation failed: {error[:200]}",
            name="generate",
        )
        return Command(
            goto="supervisor",
            update={
                "generated_records": [],
                "error_message": error,
                "messages": [msg],
            },
        )

    real_count = sum(1 for r in records if r.identity_label == "real")
    fake_count = sum(1 for r in records if r.identity_label == "fake")

    msg = HumanMessage(
        content=f"Traffic generation complete (subgraph): {len(records)} records (real={real_count}, fake={fake_count})",
        name="generate",
    )

    return Command(
        goto="supervisor",
        update={
            "generated_records": records,
            "approval_action": "",  # reset after reject → regenerate
            "approval_hint": "",    # reset stale feedback
            "messages": [msg],
        },
    )


# ---------------------------------------------------------------------------
# Eval Worker
# ---------------------------------------------------------------------------

async def eval_worker(state: GraphState) -> Command[dict[str, Any]]:  # type: ignore[type-arg]
    """Evaluate quality of generated records (Pandera + diversity)."""
    session_id: str = state.get("session_id", "")  # type: ignore[assignment]
    _check_cancelled(session_id)

    # ── Custom streaming: stage start ──────────────────────────────────
    try:
        writer = get_stream_writer()
        writer({
            "type": "stage_start",
            "node": "eval",
            "name": "质量评估",
            "message": "Pandera 质量评估 (格式/业务/多样性)",
        })
    except RuntimeError:
        pass

    records: list[TrafficRecord] = state.get("generated_records", []) or []  # type: ignore[assignment]
    industry: str = state.get("industry", "")  # type: ignore[assignment]
    retries: int = state.get("retries", 0)  # type: ignore[assignment]
    max_retries: int = state.get("max_retries", 3)  # type: ignore[assignment]

    logger.info("[Eval Worker] session=%s retry=%d/%d", session_id, retries, max_retries)

    quality: QualityScore = evaluate_quality(records, industry)
    passed = quality.passed
    should_retry = (not passed) and (retries < max_retries)

    # ── Build self-optimization feedback (P3.7) ─────────────────────────
    # When quality fails, aggregate dimension notes into a concise,
    # actionable feedback string for the generate worker to consume.
    eval_feedback = ""
    if not passed:
        parts: list[str] = []
        if quality.format_notes:
            parts.append("● Format issues: " + "; ".join(quality.format_notes[:3]))
        if quality.business_notes:
            parts.append("● Business issues: " + "; ".join(quality.business_notes[:3]))
        if quality.diversity_notes:
            parts.append("● Diversity issues: " + "; ".join(quality.diversity_notes[:3]))
        eval_feedback = "\n".join(parts)
        logger.info("[Eval Worker] feedback for generate: %s", eval_feedback[:120])

    status_text = "Passed" if passed else f"Failed (attempt {retries + 1})"
    msg = HumanMessage(
        content=f"Quality evaluation: {status_text}, total={quality.total_score}",
        name="eval",
    )

    return Command(
        goto="supervisor",
        update={
            "quality_score": quality,
            "quality_passed": passed,
            "should_retry": should_retry,
            "retries": retries + 1 if should_retry else retries,
            "eval_feedback": eval_feedback,
            "messages": [msg],
        },
    )


# ---------------------------------------------------------------------------
# Identity Worker
# ---------------------------------------------------------------------------

async def identity_worker(state: GraphState) -> Command[dict[str, Any]]:  # type: ignore[type-arg]
    """Perform identity-label validation on generated records."""
    session_id: str = state.get("session_id", "")  # type: ignore[assignment]
    _check_cancelled(session_id)

    # ── Custom streaming: stage start ──────────────────────────────────
    try:
        writer = get_stream_writer()
        writer({
            "type": "stage_start",
            "node": "identity",
            "name": "身份校验",
            "message": "身份标签校验 (真实用户 vs 自动化脚本)",
        })
    except RuntimeError:
        pass

    stage: Stage = state.get("stage", Stage.standard)  # type: ignore[assignment]
    records: list[TrafficRecord] = state.get("generated_records", []) or []  # type: ignore[assignment]

    logger.info("[Identity Worker] session=%s stage=%s", session_id, stage.value)

    checked = stage == Stage.full
    if checked:
        # Real identity service call would go here
        logger.info("[Identity Worker] identity check completed (mock)")
        msg = HumanMessage(
            content="Identity check completed",
            name="identity",
        )
    else:
        msg = HumanMessage(
            content="Identity check skipped (stage != full)",
            name="identity",
        )

    return Command(
        goto="supervisor",
        update={
            "identity_checked": checked,
            "messages": [msg],
        },
    )


# ---------------------------------------------------------------------------
# Approval Worker (Human-in-the-Loop)
# ---------------------------------------------------------------------------

async def approval_worker(state: GraphState) -> Command[dict[str, Any]]:  # type: ignore[type-arg]
    """Pause execution and wait for human approval of generated records.

    Uses LangGraph's ``interrupt()`` to suspend the graph.  The graph
    resumes when the frontend calls ``POST /resume/{session_id}`` with
    ``{"action": "approve" | "reject", "hint": "..."}``.
    """
    session_id: str = state.get("session_id", "")  # type: ignore[assignment]
    _check_cancelled(session_id)

    # ── Custom streaming: stage start ──────────────────────────────────
    try:
        writer = get_stream_writer()
        writer({
            "type": "stage_start",
            "node": "approval",
            "name": "人工审核",
            "message": "等待人工审核生成的流量数据",
        })
    except RuntimeError:
        pass

    records: list[TrafficRecord] = state.get("generated_records", []) or []  # type: ignore[assignment]
    quality = state.get("quality_score")
    scenario: str = state.get("scenario", "")  # type: ignore[assignment]

    # Build a summary for the reviewer
    real_count = sum(1 for r in records if r.identity_label == "real")
    fake_count = sum(1 for r in records if r.identity_label == "fake")
    anomaly_count = sum(1 for r in records if r.identity_label == "anomaly")
    total_score = getattr(quality, "total_score", 0) if quality else 0

    sample_records = []
    for r in records[:3]:
        sample_records.append({
            "method": r.method,
            "url": r.url,
            "status_code": r.status_code,
            "identity_label": r.identity_label,
            "rtt": round(r.rtt, 2) if r.rtt else None,
            "duration": round(r.duration, 2) if r.duration else None,
        })

    interrupt_payload = {
        "type": "approval_required",
        "session_id": session_id,
        "scenario": scenario,
        "record_count": len(records),
        "real_count": real_count,
        "fake_count": fake_count,
        "anomaly_count": anomaly_count,
        "quality_score": total_score,
        "sample_records": sample_records,
    }

    logger.info("[Approval Worker] session=%s waiting for human approval (%d records, score=%.1f)",
                session_id, len(records), total_score)

    # ── HITL: pause and wait for human decision ────────────────────────
    decision: dict[str, Any] = interrupt(interrupt_payload)  # type: ignore[assignment]

    action: str = decision.get("action", "reject")
    hint: str = decision.get("hint", "")

    logger.info("[Approval Worker] session=%s human decision: %s (hint=%s)",
                session_id, action, hint[:80] if hint else "")

    if action == "approve":
        msg = HumanMessage(
            content="人工审核通过",
            name="approval",
        )
    else:
        msg = HumanMessage(
            content=f"人工审核驳回: {hint}" if hint else "人工审核驳回",
            name="approval",
        )

    return Command(
        goto="supervisor",
        update={
            "approval_action": action,
            "approval_hint": hint,
            "messages": [msg],
        },
    )
