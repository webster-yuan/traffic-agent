from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.data.industries import INDUSTRY_KEYS


class Stage(str, Enum):
    quick = "quick"
    standard = "standard"
    full = "full"


class SessionStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# Industry Literal type — MUST stay in sync with INDUSTRY_KEYS in app/data/industries.py
# Test test_industry_keys_sync() verifies alignment
Industry = Literal[
    "government", "ecommerce", "short_video",
    "ride_hailing", "logistics", "delivery",
    "finance", "healthcare", "media",
    "social", "gaming", "custom",
]


class IndustryItem(BaseModel):
    """Simplified industry info for frontend API."""
    key: str
    label: str
    scenario: str


class TrafficGenerateRequest(BaseModel):
    industry: Industry
    count: int = Field(default=100, ge=1, le=10000)
    stage: Stage = Field(default=Stage.standard)


class TrafficResumeRequest(BaseModel):
    """Request to resume a HITL-paused graph."""
    action: Literal["approve", "reject"]
    hint: str = Field(default="", description="Feedback hint when rejecting")


class QualityScore(BaseModel):
    format_score: float
    business_score: float
    diversity_score: float
    total_score: float
    passed: bool
    format_notes: list[str] = Field(default_factory=list)
    business_notes: list[str] = Field(default_factory=list)
    diversity_notes: list[str] = Field(default_factory=list)


class TrafficRecord(BaseModel):
    id: str
    method: str
    url: str
    status_code: int
    timestamp: datetime
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    header: dict
    req_body: dict | None
    resp_body: dict | None
    rtt: float | None
    duration: float | None
    user_agent: str | None
    referer: str | None
    identity_label: Literal["real", "fake", "anomaly"]


class TrafficGenerateResponse(BaseModel):
    success: bool
    session_id: str
    total_count: int
    quality_score: QualityScore | None  # None when GraphInterrupt pauses graph
    generated_data: list[TrafficRecord]
    processing_time_ms: int


class SessionSummary(BaseModel):
    session_id: str
    industry: str
    scenario: str
    stage: Stage
    status: SessionStatus
    requested_count: int
    record_count: int
    quality_score: float | None
    quality_detail: QualityScore | None = None
    trace_thread_id: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str | None = None


class BatchTaskItem(BaseModel):
    industry: Industry
    count: int = Field(default=100, ge=1, le=10000)
    stage: Stage = Field(default=Stage.standard)


class BatchGenerateRequest(BaseModel):
    tasks: list[BatchTaskItem] = Field(..., min_length=1, max_length=10)


class BatchTaskStatus(BaseModel):
    index: int
    industry: str
    stage: Stage
    count: int
    session_id: str
    status: SessionStatus
    progress: int
    error_message: str | None = None


class BatchStatusResponse(BaseModel):
    batch_id: str
    tasks: list[BatchTaskStatus]
    finished: bool


# ---------------------------------------------------------------------------
# Structured output models (P1.3 — with_structured_output)
# ---------------------------------------------------------------------------

class TrafficRecordItem(BaseModel):
    """Single traffic record for structured LLM generation output."""

    id: str = Field(description="UUID format string")
    method: Literal["GET", "POST", "PUT", "DELETE"] = Field(description="HTTP method")
    url: str = Field(description="Complete HTTPS URL matching industry domain")
    status_code: int = Field(ge=100, le=599, description="HTTP status code")
    timestamp: str = Field(description="ISO-8601 timestamp")
    src_ip: str = Field(description="Client IP, 192.168.x.x format")
    src_port: int = Field(ge=1024, le=65535, description="Ephemeral source port")
    dst_ip: str = Field(description="Server IP, 10.0.x.x format")
    dst_port: int = Field(description="Service port: 80/443/8080/8443")
    header: dict = Field(description="HTTP request headers as JSON object")
    req_body: Optional[dict] = Field(default=None, description="Request body, null for GET/DELETE")
    resp_body: Optional[dict] = Field(default=None, description="Response body")
    rtt: Optional[float] = Field(default=None, ge=0, description="Round-trip time in ms")
    duration: Optional[float] = Field(default=None, ge=0, description="Request duration in ms")
    user_agent: Optional[str] = Field(default=None, description="User-Agent header string")
    referer: Optional[str] = Field(default=None, description="Referer header")
    identity_label: Literal["real", "fake", "anomaly"] = Field(
        description="Identity: real=browser, fake=script, anomaly=attack"
    )


class TrafficGenerationOutput(BaseModel):
    """Structured output wrapper for LLM traffic generation."""

    records: list[TrafficRecordItem] = Field(description="Generated traffic records")


class GenerationHint(BaseModel):
    """Structured hint from LLM for generation strategy."""

    strategy: str = Field(description="One-sentence generation strategy (≤30 Chinese chars)")


class RouterDecision(BaseModel):
    """Supervisor routing decision."""

    next: Literal["rag", "generate", "eval", "identity", "approval", "FINISH"] = Field(
        description="Next worker to invoke, or FINISH to end"
    )
    reason: str = Field(description="Why this worker was chosen (Chinese, ≤50 chars)")


# ---------------------------------------------------------------------------
# Checkpoint Replay models (P4.1 — Time Travel)
# ---------------------------------------------------------------------------

REPLAY_FROM_NODES = Literal["rag", "generate", "eval", "identity"]


class TrafficReplayRequest(BaseModel):
    """Request to replay a session from a specific checkpoint node."""

    session_id: str = Field(description="Original session ID to replay from")
    from_node: REPLAY_FROM_NODES = Field(
        description="Replay starting after this node completes (e.g. 'rag' replays from generate onward)"
    )
    hint_override: str | None = Field(
        default=None,
        description="Optional custom hint/prompt to inject before regeneration",
    )


class CheckpointItem(BaseModel):
    """A single checkpoint snapshot."""

    checkpoint_id: str
    step: int
    node_name: str
    timestamp: str


class CheckpointListResponse(BaseModel):
    """Response wrapper for checkpoint listing."""

    session_id: str
    checkpoints: list[CheckpointItem]
