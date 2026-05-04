"""Unified LLM factory — single source of truth for ChatOllama instantiation.

Replaces scattered ``ChatOllama(...)`` calls across supervisor.py,
generate_subgraph.py, langchain_service.py, and generator.py.
"""

from functools import lru_cache

from langchain_ollama import ChatOllama

from app.core.config import settings


@lru_cache()
def get_ollama_llm(
    temperature: float = 0.3,
    num_predict: int = 4096,
) -> ChatOllama:
    """Return a cached ChatOllama instance configured from settings.

    Args:
        temperature: LLM sampling temperature (0.0-1.0).
        num_predict: Maximum tokens to generate.
    """
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=temperature,
        num_predict=num_predict,
        timeout=settings.llm_timeout,
    )
