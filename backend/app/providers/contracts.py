from datetime import date, datetime
from typing import Protocol

from app.domain.research import (
    AIInterpretation,
    MarketSnapshot,
    NewsSnapshot,
    ResearchMetric,
)


class MarketDataProvider(Protocol):
    name: str

    def fetch_daily_snapshot(
        self,
        symbol: str,
        start_session: date,
        end_session: date,
        retrieved_at: datetime,
    ) -> MarketSnapshot: ...


class NewsProvider(Protocol):
    name: str

    def fetch_company_news(
        self, symbol: str, as_of: datetime, limit: int
    ) -> NewsSnapshot: ...


class InterpretationProvider(Protocol):
    name: str

    def interpret(
        self, *, symbol: str, metrics: list[ResearchMetric], news: NewsSnapshot
    ) -> AIInterpretation: ...
