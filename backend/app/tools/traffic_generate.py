"""Traffic generation tool — calls the LLM to produce traffic records."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.schemas import TrafficGenerationOutput, TrafficRecordItem
from app.services.generator import _get_examples, _industry_context

logger = logging.getLogger(__name__)


class TrafficGenerateInput(BaseModel):
    industry: str = Field(description="Industry key, e.g. ecommerce")
    scenario: str = Field(description="Business scenario description")
    count: int = Field(default=10, ge=1, le=100, description="Number of records")


class TrafficGenerateTool(BaseTool):
    """Invoke the LLM to generate synthetic network-traffic records.

    The tool builds a system prompt with industry context and few-shot
    examples, then calls the Ollama model to produce structured output.
    """

    name: str = "traffic_generate"
    description: str = (
        "Generate synthetic network traffic records for a given industry "
        "and scenario. Returns a JSON array of TrafficRecord objects. "
        "Use after RAG search has retrieved industry examples."
    )
    args_schema: type[BaseModel] = TrafficGenerateInput

    def _build_prompt(self, industry: str, scenario: str, count: int, examples_str: str) -> str:
        return (
            f"你是网络流量数据生成助手。根据以下行业和场景信息，生成真实的流量数据。\n\n"
            f"行业: {industry}\n"
            f"场景: {scenario}\n"
            f"典型接口特征: {_industry_context(industry)}\n\n"
            f"输出格式要求:\n"
            f"生成 {count} 条流量记录，输出为 JSON 对象，包含 records 数组。\n"
            f"每条记录包含: id(UUID), method(GET/POST/PUT/DELETE), url(完整HTTPS URL),\n"
            f"status_code(100-599), timestamp(ISO-8601), src_ip(192.168.x.x),\n"
            f"src_port(1024-65535), dst_ip(10.0.x.x), dst_port(80/443/8080/8443),\n"
            f"header(JSON对象), req_body(JSON或null), resp_body(JSON或null),\n"
            f"rtt(ms或null), duration(ms), user_agent(字符串或null),\n"
            f"referer(字符串或null), identity_label(real=真人/fake=脚本/anomaly=异常)\n\n"
            f"重要要求:\n"
            f"1. 约25%流量为自动化脚本(fake)，User-Agent包含python/go/curl/scrapy\n"
            f"2. 约75%为正常浏览器流量(real)\n"
            f"3. anomaly约5%，须有异常特征(5xx状态码/高延迟/非常规端口)\n\n"
            f"参考样例:\n{examples_str}"
        )

    def _run(self, industry: str, scenario: str, count: int = 10) -> str:
        try:
            examples = _get_examples(industry)
            examples_str = "\n".join(json.dumps(e, ensure_ascii=False) for e in examples)
            prompt = self._build_prompt(industry, scenario, count, examples_str)

            llm = ChatOllama(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                temperature=0.3,
                timeout=getattr(settings, "llm_timeout", 300),
            )

            # Try structured output first; fall back to raw JSON
            try:
                structured_llm = llm.with_structured_output(TrafficGenerationOutput, method="json_mode")
                result: TrafficGenerationOutput = structured_llm.invoke(prompt)
                records = [r.model_dump() for r in result.records[:count]]
                return json.dumps(records, ensure_ascii=False)
            except Exception:
                logger.info("Structured output failed, falling back to raw JSON parse")
                response = llm.invoke(prompt)
                content = getattr(response, "content", "")
                records = json.loads(content.strip() if content else "[]")
                if isinstance(records, dict) and "records" in records:
                    records = records["records"]
                return json.dumps(records[:count], ensure_ascii=False)

        except Exception as exc:
            logger.exception("TrafficGenerateTool failed: %s", exc)
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    async def _arun(self, industry: str, scenario: str, count: int = 10) -> str:
        try:
            examples = _get_examples(industry)
            examples_str = "\n".join(json.dumps(e, ensure_ascii=False) for e in examples)
            prompt = self._build_prompt(industry, scenario, count, examples_str)

            llm = ChatOllama(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                temperature=0.3,
                timeout=getattr(settings, "llm_timeout", 300),
            )

            timeout = getattr(settings, "llm_timeout", 300)
            try:
                structured_llm = llm.with_structured_output(TrafficGenerationOutput, method="json_mode")
                result: TrafficGenerationOutput = await asyncio.wait_for(
                    structured_llm.ainvoke(prompt), timeout=timeout
                )
                records = [r.model_dump() for r in result.records[:count]]
                return json.dumps(records, ensure_ascii=False)
            except Exception:
                logger.info("Structured output failed, falling back to raw JSON parse")
                response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=timeout)
                content = getattr(response, "content", "")
                records = json.loads(content.strip() if content else "[]")
                if isinstance(records, dict) and "records" in records:
                    records = records["records"]
                return json.dumps(records[:count], ensure_ascii=False)

        except Exception as exc:
            logger.exception("TrafficGenerateTool async failed: %s", exc)
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
