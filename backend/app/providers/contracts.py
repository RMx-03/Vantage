from datetime import date, datetime
from typing import Protocol

from app.domain.research import (
    AIInterpretation,
    FilingsSnapshot,
    FundamentalsSnapshot,
    MacroSnapshot,
    MarketSnapshot,
    NewsItem,
    NewsSnapshot,
    PriceCrossCheckSnapshot,
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
        *,
        context_symbols: tuple[str, ...] = (),
    ) -> MarketSnapshot: ...


class NewsProvider(Protocol):
    name: str

    def fetch_company_news(
        self,
        symbol: str,
        cutoff: datetime,
        retrieved_at: datetime,
        lookback_days: int,
        limit: int,
    ) -> NewsSnapshot: ...


class FilingsProvider(Protocol):
    name: str

    def fetch_filing_evidence(
        self,
        symbol: str,
        cutoff: datetime,
        retrieved_at: datetime,
        lookback_days: int,
    ) -> FilingsSnapshot: ...


class FundamentalsProvider(Protocol):
    name: str

    def fetch_fundamentals(
        self, symbol: str, retrieved_at: datetime, *, cutoff: datetime | None = None
    ) -> FundamentalsSnapshot: ...


class MacroProvider(Protocol):
    name: str

    def fetch_macro(
        self, end_session: date, retrieved_at: datetime
    ) -> MacroSnapshot: ...


class PriceCrossCheckProvider(Protocol):
    name: str

    def fetch_adjusted_closes(
        self,
        symbol: str,
        start_session: date,
        end_session: date,
        retrieved_at: datetime,
    ) -> PriceCrossCheckSnapshot: ...


class InterpretationProvider(Protocol):
    name: str
    model: str
    enabled: bool

    def interpret(
        self, *, symbol: str, metrics: list[ResearchMetric], evidence: list[NewsItem]
    ) -> AIInterpretation | None: ...
