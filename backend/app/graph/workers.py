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
from langgraph.types import Command

from app.core.state import is_cancelled
from app.graph.generate_subgraph import build_generate_subgraph
from app.graph.state import GraphState
from app.models.schemas import QualityScore, Stage, TrafficRecord
from app.services.generator import (
    _get_examples,
    evaluate_quality,
    infer_scenario,
)

logger = logging.getLogger(__name__)


def _check_cancelled(session_id: str) -> None:
    if is_cancelled(session_id):
        raise RuntimeError("Task cancelled by user")


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
            "name": "RAGæ£ç´¢",
            "message": f"æ£ç´¢ {industry} è¡ä¸æ¡ä¾å¹¶æ¨æ­åºæ¯",
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
        content=f"RAG完成: 行业={industry}, 场景={scenario}, 加载{len(retrieved)}条示例",
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
            "name": "æµéçæ",
            "message": f"æ ¹æ®åºæ¯åæ¡ä¾è°ç¨ LLM çæ {count} æ¡æµéè®°å½",
        })
    except RuntimeError:
        pass

    stage: Stage = state.get("stage", Stage.standard)  # type: ignore[assignment]
    industry: str = state.get("industry", "")  # type: ignore[assignment]
    scenario: str = state.get("scenario", "")  # type: ignore[assignment]

    logger.info("[Generate Worker] session=%s count=%d (via subgraph)", session_id, count)

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
    }

    subgraph = build_generate_subgraph()
    result = await subgraph.ainvoke(sub_state)

    records: list[TrafficRecord] = result.get("records", []) or []
    error: str = result.get("error", "") or ""

    if error and not records:
        msg = HumanMessage(
            content=f"流量生成失败: {error[:200]}",
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
        content=f"流量生成完成(subgraph): 共{len(records)}条 (真实{real_count}, 脚本{fake_count})",
        name="generate",
    )

    return Command(
        goto="supervisor",
        update={
            "generated_records": records,
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

    status_text = "通过" if passed else f"未通过(第{retries + 1}次)"
    msg = HumanMessage(
        content=f"质量评估: {status_text}, 总分={quality.total_score}",
        name="eval",
    )

    return Command(
        goto="supervisor",
        update={
            "quality_score": quality,
            "quality_passed": passed,
            "should_retry": should_retry,
            "retries": retries + 1 if should_retry else retries,
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
            content="身份校验完成",
            name="identity",
        )
    else:
        msg = HumanMessage(
            content="跳过身份校验 (stage != full)",
            name="identity",
        )

    return Command(
        goto="supervisor",
        update={
            "identity_checked": checked,
            "messages": [msg],
        },
    )
