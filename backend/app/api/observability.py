import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.services.report_service import generate_report_html
from app.data.industries import get_industries_for_frontend
from app.services.system_metrics import get_metrics
from app.services.token_counter import get_token_counter

router = APIRouter()


@router.get("/report/{session_id}")
async def get_report(session_id: str):
    """Return an HTML report for a completed session."""
    html = await generate_report_html(session_id)
    if html is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return HTMLResponse(content=html, status_code=200)


@router.get("/industries")
async def get_industries():
    """Return industry configuration list for frontend consumption."""
    from app.models.schemas import IndustryItem
    data = get_industries_for_frontend()
    return [IndustryItem(**item) for item in data]


@router.get("/metrics")
async def get_system_metrics() -> dict:
    """Return system performance metrics."""
    metrics = get_metrics().stats()
    token_stats = get_token_counter().stats()
    return {
        **metrics,
        "token_usage": token_stats,
        "concurrency": {
            "max_slots": 3,
        },
    }


@router.get("/model-info")
async def get_model_info() -> dict:
    """Return current LLM model configuration and capabilities."""
    from app.core.config import settings
    return {
        "model_name": settings.ollama_model,
        "model": settings.ollama_model,
        "provider": f"Ollama ({settings.ollama_base_url})",
        "base_url": settings.ollama_base_url,
        "context_window": 32768,
        "context_window_estimate": 32768,
        "max_retries": settings.max_retry_count,
        "llm_timeout_seconds": settings.llm_timeout,
        "capabilities": [
            "structured_output_json_mode",
            "streaming",
            "tool_calling_via_langgraph",
        ],
        "supported_stages": ["quick", "standard", "full"],
        "stages": ["quick", "standard", "full"],
        "quality_dimensions": ["format", "business", "diversity"],
        "quality_threshold": 70,
    }
