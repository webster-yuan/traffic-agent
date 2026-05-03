"""Nested StateGraph for traffic generation (P2.4 — Subgraph Modularity).

Encapsulates the three-step generation pipeline as an independently
compilable subgraph:

    START → prepare_prompt → call_llm → parse_result → END

This demonstrates LangGraph's subgraph nesting capability:
the parent Supervisor-Worker graph invokes this subgraph as a
self-contained unit, isolating prompt engineering, LLM invocation,
and output parsing concerns.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from langchain_ollama import ChatOllama
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.models.schemas import Stage, TrafficRecord
from app.services.generator import _get_examples, _industry_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subgraph State
# ---------------------------------------------------------------------------


class GenerateSubState(TypedDict, total=False):
    """State scoped to the generate subgraph.

    Only fields relevant to traffic generation are included,
    keeping the subgraph decoupled from parent orchestration concerns.
    """

    industry: str
    scenario: str
    count: int
    stage: Stage
    # --- internal pipeline fields ---
    prompt: str
    raw_response: str
    records: list[TrafficRecord]
    error: str


# ---------------------------------------------------------------------------
# Node 1: prepare_prompt
# ---------------------------------------------------------------------------


def _fix_json(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("Empty content")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text)
        text = text.strip("`")
    text = text.replace("'", '"')
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


async def prepare_prompt_node(state: GenerateSubState) -> dict[str, Any]:
    """Build the LLM prompt from industry metadata and examples."""
    industry: str = state.get("industry", "")  # type: ignore[assignment]
    scenario: str = state.get("scenario", "")  # type: ignore[assignment]
    count: int = state.get("count", 10)  # type: ignore[assignment]

    examples = _get_examples(industry)
    examples_str = "\n".join([json.dumps(e, ensure_ascii=False) for e in examples])

    # ── Custom streaming: notify progress ─────────────────────────────
    try:
        writer = get_stream_writer()
        writer({
            "type": "generate_progress",
            "phase": "prepare",
            "message": f"正在构建提示词 (行业={industry}, 场景={scenario})",
            "industry": industry,
            "count": count,
        })
    except RuntimeError:
        pass  # stream_mode="custom" not enabled in sync invoke

    prompt = f"""你是网络流量数据生成助手。根据以下行业和场景信息，生成真实的流量数据。

行业: {industry}
场景: {scenario}
典型接口特征: {_industry_context(industry)}

输出格式要求:
生成 {count} 条流量记录，每条包含以下字段:
- id: UUID格式字符串
- method: HTTP方法 (GET/POST/PUT/DELETE)
- url: 完整的HTTPS URL
- status_code: HTTP状态码
- timestamp: ISO格式时间
- src_ip: 客户端IP (192.168.x.x)
- src_port: 客户端端口 (1024-65535)
- dst_ip: 服务端IP (10.0.x.x)
- dst_port: 服务端端口 (80/443/8080/8443)
- header: HTTP请求头 (JSON格式)
- req_body: 请求体 (JSON格式，可为null)
- resp_body: 响应体 (JSON格式)
- rtt: 往返时延(毫秒，可为null)
- duration: 请求耗时(毫秒)
- user_agent: User-Agent字符串
- referer: Referer头 (可为null)
- identity_label: 身份标签 (real=真人, fake=自动化脚本)

重要要求:
1. 约25%流量为自动化脚本(fake)，User-Agent包含python/go/curl/scrapy
2. 约75%为正常浏览器流量(real)
3. 直接输出JSON数组，不要其他文字

参考样例:
{examples_str}"""

    logger.info("[GenerateSub] prompt prepared: industry=%s, count=%d, chars=%d",
                industry, count, len(prompt))
    return {"prompt": prompt}


# ---------------------------------------------------------------------------
# Node 2: call_llm
# ---------------------------------------------------------------------------


async def call_llm_node(state: GenerateSubState) -> dict[str, Any]:
    """Invoke ChatOllama with the prepared prompt."""
    prompt: str = state.get("prompt", "")  # type: ignore[assignment]

    if not prompt:
        return {"error": "prompt is empty", "raw_response": ""}

    llm = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0.3,
        timeout=getattr(settings, "llm_timeout", 300),
    )

    timeout = getattr(settings, "llm_timeout", 300)
    logger.info("[GenerateSub] calling LLM (model=%s, timeout=%ds)", settings.ollama_model, timeout)

    # ── Custom streaming: LLM call started ────────────────────────────
    try:
        writer = get_stream_writer()
        writer({
            "type": "generate_progress",
            "phase": "llm_call",
            "message": f"正在调用 LLM 生成流量数据 (超时={timeout}s)...",
            "timeout": timeout,
        })
    except RuntimeError:
        pass

    try:
        response = await asyncio.wait_for(
            llm.ainvoke(f"{prompt}\n\n请生成流量数据"),
            timeout=timeout,
        )
        content: str = getattr(response, "content", "")
        if not content:
            return {"error": "LLM returned empty content", "raw_response": ""}
        logger.info("[GenerateSub] LLM response received: %d chars", len(content))

        # ── Custom streaming: LLM response received ───────────────────
        try:
            writer = get_stream_writer()
            writer({
                "type": "generate_progress",
                "phase": "llm_done",
                "message": f"LLM 响应已收到 ({len(content)} 字符)，开始解析...",
                "chars": len(content),
            })
        except RuntimeError:
            pass

        return {"raw_response": content, "error": ""}
    except asyncio.TimeoutError:
        logger.error("[GenerateSub] LLM call timed out after %ds", timeout)
        return {"error": f"LLM call timed out after {timeout}s", "raw_response": ""}
    except Exception as e:
        logger.exception("[GenerateSub] LLM call failed")
        return {"error": str(e), "raw_response": ""}


# ---------------------------------------------------------------------------
# Node 3: parse_result
# ---------------------------------------------------------------------------


async def parse_result_node(state: GenerateSubState) -> dict[str, Any]:
    """Parse LLM JSON response into validated TrafficRecord list."""
    raw: str = state.get("raw_response", "")  # type: ignore[assignment]
    error: str = state.get("error", "")  # type: ignore[assignment]
    count: int = state.get("count", 10)  # type: ignore[assignment]

    if error:
        logger.warning("[GenerateSub] skipped parse due to upstream error: %s", error[:80])
        return {"records": [], "error": error}

    if not raw:
        return {"records": [], "error": "empty LLM response"}

    # --- JSON parse ----------------------------------------------------------
    try:
        result = json.loads(raw.strip())
    except json.JSONDecodeError:
        logger.warning("[GenerateSub] JSON parse failed, attempting repair")
        try:
            fixed = _fix_json(raw.strip())
            result = json.loads(fixed)
        except Exception as e:
            logger.error("[GenerateSub] JSON repair also failed: %s", e)
            return {"records": [], "error": f"JSON parse error: {e}"}

    if not isinstance(result, list):
        result = [result]

    # --- Build TrafficRecord list --------------------------------------------
    now = datetime.now(timezone.utc)
    records: list[TrafficRecord] = []
    total = min(count, len(result))
    for i, item in enumerate(result[:count]):
        record = TrafficRecord(
            id=item.get("id", str(uuid.uuid4())),
            method=item.get("method", "GET"),
            url=item.get("url", "https://api.example.com/test"),
            status_code=item.get("status_code", 200),
            timestamp=datetime.fromisoformat(
                item["timestamp"].replace("Z", "+00:00")
            ) if item.get("timestamp") else now - timedelta(seconds=i),
            src_ip=item.get("src_ip", "192.168.1.1"),
            src_port=item.get("src_port", 8080),
            dst_ip=item.get("dst_ip", "10.0.0.1"),
            dst_port=item.get("dst_port", 443),
            header=item.get("header", {}),
            req_body=item.get("req_body"),
            resp_body=item.get("resp_body"),
            rtt=item.get("rtt"),
            duration=item.get("duration"),
            user_agent=item.get("user_agent", "Mozilla/5.0"),
            referer=item.get("referer"),
            identity_label=item.get("identity_label", "real"),
        )
        records.append(record)

        # ── Custom streaming: per‑record parse progress (every 5) ──────
        parsed = i + 1
        if parsed % 5 == 0 or parsed == total:
            try:
                writer = get_stream_writer()
                writer({
                    "type": "generate_progress",
                    "phase": "parse",
                    "message": f"已解析 {parsed}/{total} 条记录...",
                    "parsed": parsed,
                    "total": total,
                })
            except RuntimeError:
                pass

    real_count = sum(1 for r in records if r.identity_label == "real")
    fake_count = sum(1 for r in records if r.identity_label == "fake")
    logger.info("[GenerateSub] parsed %d records (real=%d, fake=%d)", len(records), real_count, fake_count)
    return {"records": records, "error": ""}


# ---------------------------------------------------------------------------
# Subgraph Builder
# ---------------------------------------------------------------------------


def build_generate_subgraph() -> StateGraph:
    """Build the traffic-generation subgraph as a standalone StateGraph.

    Returns a *compiled* graph that can be invoked with ``ainvoke()``
    or embedded as a node in the parent Supervisor-Worker graph.
    """
    builder = StateGraph(GenerateSubState)

    builder.add_node("prepare_prompt", prepare_prompt_node)
    builder.add_node("call_llm", call_llm_node)
    builder.add_node("parse_result", parse_result_node)

    builder.add_edge(START, "prepare_prompt")
    builder.add_edge("prepare_prompt", "call_llm")
    builder.add_edge("call_llm", "parse_result")
    builder.add_edge("parse_result", END)

    return builder.compile()
