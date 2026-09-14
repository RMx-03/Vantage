import math
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Symbol = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9.]{0,9}$")]


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ResearchStatus(StrEnum):
    INFORMATIONAL = "informational"
    REVIEW = "review"
    INSUFFICIENT_DATA = "insufficient_data"
    FAILED = "failed"


class OverallQuality(StrEnum):
    SUFFICIENT = "sufficient"
    DEGRADED = "degraded"
    INSUFFICIENT = "insufficient"


class ComponentQuality(StrEnum):
    FRESH = "fresh"
    PARTIAL = "partial"
    STALE = "stale"
    MISSING = "missing"
    FAILED = "failed"


class ModelQuality(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    NOT_RUN = "not_run"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "created_at",
        "completed_at",
        "as_of",
        "retrieved_at",
        "event_time",
        "coverage_start",
        "coverage_end",
        check_fields=False,
    )
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class ResearchRunRequest(StrictModel):
    symbol: Symbol

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> str:
        return str(value).strip().upper()


class ResearchMetric(StrictModel):
    key: str
    label: str
    value: float | int | None
    unit: Literal["ratio", "percent", "usd", "count", "sessions"]
    window_sessions: int | None
    as_of: datetime
    calculation_version: Literal["eod-metrics-v1"]
    quality: ComponentQuality

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float | int | None) -> float | int | None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("metric value must be finite")
        return value


class Reason(StrictModel):
    code: str
    label: str
    severity: Literal["info", "warning", "blocking"]
    description: str
    metric_keys: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    policy_version: Literal["research-policy-v1"] = "research-policy-v1"
    threshold: float | None = None


class AIInterpretation(StrictModel):
    sentiment_label: Literal["positive", "mixed", "neutral", "negative", "unavailable"]
    sentiment_score: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    summary: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    abstained: bool = False
    abstention_reason: str | None = None


class DailyBar(StrictModel):
    symbol: Symbol
    session_date: date
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    adjusted_close: float = Field(gt=0, allow_inf_nan=False)
    volume: int = Field(ge=0)
    currency: Literal["USD"]
    provider: str
    retrieved_at: datetime
    adjustment_state: Literal["split_adjusted", "split_and_dividend_adjusted", "unadjusted"]


class MarketSnapshot(StrictModel):
    symbol: Symbol
    bars: list[DailyBar]
    provider: str
    retrieved_at: datetime
    as_of: datetime
    latest_completed_session: date
    content_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    quality: ComponentQuality = ComponentQuality.FRESH
    error_code: str | None = None


class NewsItem(StrictModel):
    evidence_id: str
    provider: str
    publisher: str | None = None
    title: str
    url: str | None = None
    event_time: datetime | None = None
    retrieved_at: datetime
    content_hash: str | None = None


class NewsSnapshot(StrictModel):
    symbol: Symbol
    items: list[NewsItem]
    provider: str
    retrieved_at: datetime
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    quality: ComponentQuality
    error_code: str | None = None


class EvidenceSource(NewsItem):
    source_type: Literal["news"] = "news"


class DataQuality(StrictModel):
    overall: OverallQuality
    prices: ComponentQuality
    news: ComponentQuality
    model: ModelQuality


class ModelInfo(StrictModel):
    provider: str
    model: str
    prompt_version: Literal["research-interpretation-v1"]
    failure_code: str | None = None


class VersionInfo(StrictModel):
    response_schema: Literal["research-run-response-v1"]
    workflow: Literal["eod-research-v1"]
    metrics: Literal["eod-metrics-v1"]
    policy: Literal["research-policy-v1"]
    code: str


class ResearchRun(StrictModel):
    run_id: UUID
    symbol: Symbol
    created_at: datetime
    completed_at: datetime | None
    as_of: datetime | None
    workflow_status: WorkflowStatus
    research_status: ResearchStatus | None
    summary: str | None
    reasons: list[Reason]
    metrics: list[ResearchMetric]
    data_quality: DataQuality | None
    sources: list[EvidenceSource]
    warnings: list[str]
    model_info: ModelInfo | None
    versions: VersionInfo
    error_code: str | None = None
    error_message_safe: str | None = None


class ResearchRunPage(StrictModel):
    items: list[ResearchRun]
    next_cursor: str | None
