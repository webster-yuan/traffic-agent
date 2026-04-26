import os
import logging
from typing import Any

from app.core.config import settings
from app.core.state import is_cancelled
from app.graph.state import GraphState
from app.models.schemas import QualityScore, Stage
from app.services.generator import evaluate_quality, generate_records_by_llm, infer_scenario
from app.services.langchain_service import build_generation_hint

logger = logging.getLogger(__name__)

if os.environ.get("LANGCHAIN_TRACING_V2") == "true":
    from langsmith.run_helpers import traceable
else:
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


def _check_cancelled(session_id: str) -> None:
    """检查任务是否被取消"""
    if is_cancelled(session_id):
        raise RuntimeError("Task cancelled by user")


def _default_quality() -> QualityScore:
    return QualityScore(
        format_score=0,
        business_score=0,
        diversity_score=0,
        total_score=0,
        passed=False,
    )


def _record_field(record: Any, field: str) -> Any:
    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


def _summarize_generate_output(state: GraphState) -> dict[str, Any]:
    records = state.get("generated_records", []) or []
    identity_counts: dict[str, int] = {}
    for record in records:
        identity = _record_field(record, "identity_label") or "unknown"
        identity_counts[str(identity)] = identity_counts.get(str(identity), 0) + 1

    sample_record = None
    if records:
        first = records[0]
        sample_record = {
            "method": _record_field(first, "method"),
            "url": _record_field(first, "url"),
            "status_code": _record_field(first, "status_code"),
            "identity_label": _record_field(first, "identity_label"),
            "user_agent": _record_field(first, "user_agent"),
        }

    hint = ""
    for case in reversed(state.get("retrieved_cases", []) or []):
        if isinstance(case, dict) and case.get("type") == "llm_hint":
            hint = str(case.get("content", ""))
            break

    stage = state.get("stage")
    return {
        "session_id": state.get("session_id"),
        "industry": state.get("industry"),
        "scenario": state.get("scenario"),
        "stage": getattr(stage, "value", stage),
        "requested_count": state.get("count"),
        "generated_count": len(records),
        "identity_counts": identity_counts,
        "hint": hint[:120],
        "sample_record": sample_record,
    }


@traceable(name="rag_node")
def rag_node(state: GraphState) -> GraphState:
    _check_cancelled(state["session_id"])
    logger.info(f"session_id={state['session_id']} RAG检索开始")

    state["scenario"] = infer_scenario(state["industry"])
    state["retrieved_cases"] = [
        {"industry": state["industry"], "scenario": state["scenario"], "content": "mock_case"}
    ]

    if "quality_score" not in state:
        state["quality_score"] = _default_quality()

    logger.info(f"session_id={state['session_id']} RAG检索完成: 场景={state['scenario']}")
    return state


@traceable(name="generate_node", process_outputs=_summarize_generate_output)
def generate_node(state: GraphState) -> GraphState:
    _check_cancelled(state["session_id"])
    logger.info(f"session_id={state['session_id']} 流量生成开始")

    hint = build_generation_hint(
        industry=state["industry"],
        scenario=state["scenario"],
        count=state["count"],
    )
    state["retrieved_cases"].append({"type": "llm_hint", "content": hint})

    state["generated_records"] = generate_records_by_llm(
        state["count"], state["stage"], state["industry"], state["scenario"]
    )

    real_count = sum(1 for r in state["generated_records"] if r.identity_label == "real")
    fake_count = sum(1 for r in state["generated_records"] if r.identity_label == "fake")
    logger.info(f"session_id={state['session_id']} 流量生成完成: 共 {len(state['generated_records'])} 条, 真实 {real_count} 条, 脚本 {fake_count} 条")

    return state


@traceable(name="eval_node")
def eval_node(state: GraphState) -> GraphState:
    _check_cancelled(state["session_id"])
    logger.info(f"session_id={state['session_id']} 质量评估开始 (第 {state['retries'] + 1} 次)")

    quality = evaluate_quality(state["generated_records"], state["industry"])
    state["quality_score"] = quality
    state["quality_passed"] = quality.passed
    logger.info(f"session_id={state['session_id']} 质量评估结果: 总分={quality.total_score}, {'通过' if quality.passed else '未通过'}")

    state["should_retry"] = (not quality.passed) and (
        state["retries"] < state["max_retries"]
    )
    if state["should_retry"]:
        state["retries"] += 1
        logger.info(f"session_id={state['session_id']} 需要重试, 当前重试次数: {state['retries']}")

    return state


@traceable(name="identity_node")
def identity_node(state: GraphState) -> GraphState:
    _check_cancelled(state["session_id"])
    logger.info(f"session_id={state['session_id']} 身份校验开始")

    need_identity_check = state["stage"] == Stage.full
    if need_identity_check:
        if not settings.identity_service_enabled:
            logger.error(f"session_id={state['session_id']} 身份服务不可用")
            raise RuntimeError("Identity service unavailable, request failed")

        # 实际项目中这里会调用身份服务API
        state["identity_checked"] = True
        logger.info(f"session_id={state['session_id']} 身份校验完成")
    else:
        state["identity_checked"] = False
        logger.info(f"session_id={state['session_id']} 跳过身份校验")

    return state


def should_retry_after_eval(state: GraphState) -> str:
    if state["should_retry"]:
        return "generate"
    return "identity"
