from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


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


Industry = Literal[
    "government", "ecommerce", "short_video",
    "ride_hailing", "logistics", "delivery",
    "finance", "healthcare", "media",
    "social", "gaming", "custom",
]


class TrafficGenerateRequest(BaseModel):
    industry: Industry
    count: int = Field(default=100, ge=1, le=10000)
    stage: Stage = Field(default=Stage.standard)


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
    quality_score: QualityScore
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
