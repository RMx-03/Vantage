from typing import TypedDict
from uuid import UUID

from app.domain.research import (
    AIInterpretation,
    MarketSnapshot,
    NewsItem,
    NewsSnapshot,
    ResearchMetric,
)
from app.services.policy import PolicyResult
from app.services.run_inputs import RunInputs


class ResearchState(TypedDict, total=False):
    run_id: UUID
    user_id: UUID
    symbol: str
    market: MarketSnapshot
    news: NewsSnapshot
    inputs: RunInputs
    evidence: list[NewsItem]
    metrics: list[ResearchMetric]
    interpretation: AIInterpretation | None
    model_failure_code: str | None
    policy: PolicyResult
