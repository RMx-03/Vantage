from typing import TypedDict
from uuid import UUID

from app.domain.research import (
    AIInterpretation,
    MarketSnapshot,
    NewsSnapshot,
    ResearchMetric,
)
from app.services.policy import PolicyResult


class ResearchState(TypedDict, total=False):
    run_id: UUID
    user_id: UUID
    symbol: str
    market: MarketSnapshot
    news: NewsSnapshot
    metrics: list[ResearchMetric]
    interpretation: AIInterpretation
    model_failure_code: str | None
    policy: PolicyResult
