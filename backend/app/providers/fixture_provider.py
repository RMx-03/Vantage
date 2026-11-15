"""Keyless provider that serves recorded data for demos, tests and CI.

Prices are invented. Bars are placed on the real XNYS sessions of the requested
window so a fixture run looks current; no network or key is involved.
"""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from importlib import resources
import hashlib
import json
from typing import Any

from app.domain.research import (
    ComponentQuality,
    DailyBar,
    MarketSnapshot,
    NewsItem,
    NewsSnapshot,
)
from app.providers.contracts import MarketDataProvider, NewsProvider
from app.providers.yfinance_provider import (
    XNYS,
    snapshot_hash,
    trailing_xnys_sessions,
)


@lru_cache(maxsize=None)
def _load(name: str) -> Any:
    text = (
        resources.files("app.providers")
        .joinpath("fixtures", name)
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def _bars(
    symbol: str,
    rows: list[dict[str, Any]],
    sessions: list[date],
    retrieved_at: datetime,
) -> list[DailyBar]:
    recorded = rows[-len(sessions) :] if sessions else []
    return [
        DailyBar(
            symbol=symbol,
            session_date=session,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            adjusted_close=row["adjusted_close"],
            volume=row["volume"],
            currency="USD",
            provider="fixture",
            retrieved_at=retrieved_at,
            adjustment_state="split_and_dividend_adjusted",
        )
        for session, row in zip(sessions, recorded, strict=True)
    ]


class FixtureProvider(MarketDataProvider, NewsProvider):
    name: str = "fixture"

    def fetch_daily_snapshot(
        self,
        symbol: str,
        start_session: date,
        end_session: date,
        retrieved_at: datetime,
        *,
        context_symbols: tuple[str, ...] = (),
    ) -> MarketSnapshot:
        normalized = symbol.strip().upper()
        now = retrieved_at.astimezone(UTC)
        data = _load("market.json")
        sessions = [
            s for s in trailing_xnys_sessions(end_session) if s >= start_session
        ]
        bars = _bars(normalized, data["default"], sessions, now)
        context: dict[str, list[DailyBar]] = {}
        for ctx in context_symbols:
            ctx_symbol = ctx.strip().upper()
            rows = data["SPY"] if ctx_symbol == "SPY" else data["sector"]
            context[ctx_symbol] = _bars(ctx_symbol, rows, sessions, now)
        last = sessions[-1]
        return MarketSnapshot(
            symbol=normalized,
            bars=bars,
            provider=self.name,
            retrieved_at=now,
            as_of=XNYS.session_close(last).to_pydatetime().astimezone(UTC),
            latest_completed_session=last,
            content_hash=snapshot_hash(normalized, bars),
            quality=ComponentQuality.FRESH,
            context_bars=context,
        )

    def fetch_company_news(
        self,
        symbol: str,
        cutoff: datetime,
        retrieved_at: datetime,
        lookback_days: int,
        limit: int = 10,
    ) -> NewsSnapshot:
        normalized = symbol.strip().upper()
        cutoff_utc = cutoff.astimezone(UTC)
        now = retrieved_at.astimezone(UTC)
        window_start = cutoff_utc - timedelta(days=lookback_days)
        items: list[NewsItem] = []
        for index, rec in enumerate(_load("news.json")):
            event_time = cutoff_utc - timedelta(hours=rec["offset_hours"])
            if not window_start < event_time <= cutoff_utc:
                continue
            title = rec["title_template"].format(symbol=normalized)
            key = f"{rec['publisher']}|{title.lower()}|{event_time.isoformat()}"
            path = rec["url_path"].format(n=normalized.lower())
            items.append(
                NewsItem(
                    evidence_id=f"fixture-{normalized}-{index}",
                    provider=self.name,
                    publisher=rec["publisher"],
                    title=title,
                    summary=rec["summary_template"].format(symbol=normalized),
                    url=f"https://example.com{path}",
                    event_time=event_time,
                    retrieved_at=now,
                    content_hash=hashlib.sha256(key.encode("utf-8")).hexdigest(),
                )
            )
        items.sort(key=lambda i: i.event_time or cutoff_utc, reverse=True)
        if limit > 0:
            items = items[:limit]
        times = [i.event_time for i in items if i.event_time is not None]
        return NewsSnapshot(
            symbol=normalized,
            items=items,
            provider=self.name,
            retrieved_at=now,
            coverage_start=min(times) if times else None,
            coverage_end=max(times) if times else None,
            quality=ComponentQuality.FRESH if items else ComponentQuality.MISSING,
        )
