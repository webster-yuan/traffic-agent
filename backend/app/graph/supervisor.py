"""Supervisor agent node — the orchestrator of the multi-agent graph.

The supervisor examines the current state (messages, industry, scenario,
quality results, retry count) and decides which worker should act next.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.types import Command

from app.core.config import settings
from app.graph.state import GraphState
from app.models.schemas import RouterDecision

logger = logging.getLogger(__name__)

_WORKER_NAMES = Literal["rag", "generate", "eval", "identity", "__end__"]

_SYSTEM_PROMPT = """你是 Traffic Agent 系统的 Supervisor（主控代理）。你的职责是根据当前系统状态，
决定下一个应该执行的 Worker。

可用的 Worker：
- rag      — 检索行业流量案例和推断场景（首次必执行）
- generate — 调用 LLM 生成流量记录
- eval     — 对生成的流量进行质量评分（格式/业务/多样性）
- identity — 身份标签校验（全量模式）
- FINISH   — 所有任务完成，结束流程

决策规则：
1. 当 retrieved_cases 为空时 → 调用 rag
2. rag 完成后，generated_records 为空时 → 调用 generate
3. generate 完成后 → 调用 eval
4. eval 后：
   - 如果 quality_passed=true → 判断是否需要 identity
   - 如果 should_retry=true → 调用 generate（重新生成）
   - 如果 should_retry=false 且 quality_passed=false → 调用 FINISH（放弃重试）
5. identity_checked=true 或 stage != full → FINISH
6. 出现 error_message 非空 → FINISH

请返回 JSON 格式：{"next": "<worker>", "reason": "<决策原因>"}"""


async def supervisor_node(state: GraphState) -> Command[Any]:  # type: ignore[type-arg]
    """Decide the next worker based on current state."""

    session_id: str = state.get("session_id", "")  # type: ignore[assignment]
    industry: str = state.get("industry", "")  # type: ignore[assignment]

    messages: list = list(state.get("messages", []) or [])  # type: ignore[assignment]
    system = SystemMessage(content=_SYSTEM_PROMPT)
    all_msgs = [system] + messages

    llm = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0.1,
        timeout=getattr(settings, "llm_timeout", 300),
    )

    # Build a state summary for the supervisor to reason about
    state_summary_parts: list[str] = [
        f"session_id={session_id}",
        f"industry={industry}",
        f"scenario={state.get('scenario', '')}",
        f"stage={getattr(state.get('stage'), 'value', str(state.get('stage', '')))}",
        f"count={state.get('count', 0)}",
        f"retries={state.get('retries', 0)}/{state.get('max_retries', 3)}",
        f"retrieved_cases_count={len(state.get('retrieved_cases', []) or [])}",
        f"generated_records_count={len(state.get('generated_records', []) or [])}",
    ]

    quality = state.get("quality_score")
    if quality is not None:
        state_summary_parts.append(
            f"quality_total={getattr(quality, 'total_score', 0)}, "
            f"quality_passed={state.get('quality_passed', False)}"
        )

    state_summary_parts.append(f"should_retry={state.get('should_retry', False)}")
    state_summary_parts.append(f"identity_checked={state.get('identity_checked', False)}")

    error_msg = state.get("error_message", "")
    if error_msg:
        state_summary_parts.append(f"error={error_msg[:100]}")

    summary = "\n".join(state_summary_parts)
    logger.info("[Supervisor] state summary:\n%s", summary)

    all_msgs.append(
        HumanMessage(
            content=f"当前系统状态:\n{summary}\n\n请决定下一个 Worker。",
            name="system",
        )
    )

    try:
        structured_llm = llm.with_structured_output(RouterDecision, method="json_mode")
        decision: RouterDecision = await structured_llm.ainvoke(all_msgs)
    except Exception:
        logger.warning("[Supervisor] structured output failed, using fallback routing")
        decision = _fallback_route(state)

    next_worker = decision.next
    if next_worker == "FINISH":
        next_worker = "__end__"

    logger.info(
        "[Supervisor] routing decision: %s → %s (reason: %s)",
        session_id, next_worker, decision.reason,
    )

    ai_msg = AIMessage(
        content=f"[Supervisor] → {decision.next}: {decision.reason}",
        name="supervisor",
    )

    return Command(
        goto=next_worker,  # type: ignore[arg-type]
        update={
            "next_worker": decision.next,
            "messages": [ai_msg],
        },
    )


def _fallback_route(state: GraphState) -> RouterDecision:
    """Deterministic fallback when LLM routing fails."""
    retrieved_count = len(state.get("retrieved_cases", []) or [])  # type: ignore[arg-type]
    generated_count = len(state.get("generated_records", []) or [])  # type: ignore[arg-type]
    quality_score = state.get("quality_score")
    should_retry: bool = state.get("should_retry", False)  # type: ignore[assignment]
    quality_passed: bool = state.get("quality_passed", False)  # type: ignore[assignment]
    identity_checked: bool = state.get("identity_checked", False)  # type: ignore[assignment]
    error_msg: str = state.get("error_message", "")  # type: ignore[assignment]

    if error_msg:
        return RouterDecision(next="FINISH", reason="检测到错误，终止流程")

    if retrieved_count == 0:
        return RouterDecision(next="rag", reason="尚未检索行业案例")

    if generated_count == 0:
        return RouterDecision(next="generate", reason="案例就绪，开始生成流量")

    if quality_score is None:
        return RouterDecision(next="eval", reason="流量已生成，开始质量评估")

    if should_retry:
        return RouterDecision(next="generate", reason="质量未达标，重新生成")

    if not quality_passed:
        return RouterDecision(next="FINISH", reason="已达最大重试次数，放弃")

    # Check if identity is needed
    stage = state.get("stage")
    stage_value = getattr(stage, "value", str(stage)) if stage is not None else ""
    if stage_value == "full" and not identity_checked:
        return RouterDecision(next="identity", reason="全量模式，执行身份校验")

    return RouterDecision(next="FINISH", reason="所有步骤完成")
