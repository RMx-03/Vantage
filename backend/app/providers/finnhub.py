"""Finnhub company-news provider.

The token travels only in the ``X-Finnhub-Token`` header. It is held by the HTTP client
and appears in no attribute, repr, message or log line.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.domain.research import NewsItem, NewsSnapshot
from app.providers.http import ProviderHttp, ProviderHttpError, RateLimiter, fail
from app.providers.news_common import (
    ERROR_CODE,
    MESSAGES,
    build_item,
    build_snapshot,
    upper_symbols,
)

FINNHUB_LIMITER = RateLimiter(50, 60.0)

NEWS_URL = "https://finnhub.io/api/v1/company-news"
_NY = ZoneInfo("America/New_York")


class FinnhubNewsProvider:
    name: str = "finnhub"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = ProviderHttp(
            timeout_seconds=timeout_seconds,
            limiter=FINNHUB_LIMITER,
            headers={"X-Finnhub-Token": api_key},
            transport=transport,
            sleep=sleep,
        )

    def __repr__(self) -> str:
        return "FinnhubNewsProvider()"

    def fetch_company_news(
        self,
        symbol: str,
        cutoff: datetime,
        retrieved_at: datetime,
        lookback_days: int,
        limit: int,
    ) -> NewsSnapshot:
        primary = symbol.strip().upper()
        cutoff_utc = cutoff.astimezone(UTC)
        window_start = cutoff_utc - timedelta(days=lookback_days)
        params = {
            "symbol": primary,
            "from": window_start.astimezone(_NY).date().isoformat(),
            "to": cutoff_utc.astimezone(_NY).date().isoformat(),
        }
        try:
            deadline = self._http.deadline()
            payload = self._http.get_json(NEWS_URL, params=params, deadline=deadline)
            if not isinstance(payload, list):
                raise ProviderHttpError("malformed")
        except ProviderHttpError as err:
            raise fail(ERROR_CODE, MESSAGES, err) from None

        retrieved_utc = retrieved_at.astimezone(UTC)
        items: list[NewsItem] = []
        for raw in payload:
            item = self._item(raw, retrieved_utc)
            if item is not None:
                items.append(item)
        return build_snapshot(
            provider=self.name,
            symbol=primary,
            items=items,
            cutoff=cutoff_utc,
            retrieved_at=retrieved_utc,
            lookback_days=lookback_days,
            limit=limit,
        )

    def _item(self, raw: object, retrieved_at: datetime) -> NewsItem | None:
        if not isinstance(raw, dict):
            return None
        stamp = raw.get("datetime")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            return None
        try:
            event_time = datetime.fromtimestamp(stamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
        related = raw.get("related")
        symbols = upper_symbols(related.split(",")) if isinstance(related, str) else []
        return build_item(
            provider=self.name,
            raw_id=raw.get("id"),
            publisher=raw.get("source"),
            title=raw.get("headline"),
            summary=raw.get("summary"),
            url=raw.get("url"),
            event_time=event_time,
            symbols=symbols,
            retrieved_at=retrieved_at,
        )
