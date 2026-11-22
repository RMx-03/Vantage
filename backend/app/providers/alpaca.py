"""Alpaca SIP daily-bar market provider.

Alpaca's free plan serves SIP data only after a 15-minute delay, so the request end is
clamped to ``now - 16 minutes``. When the clamp lands before the session close, the
snapshot is built for the latest session that has closed by then and is reported as
``STALE`` against the requested session, never padded or relabelled.

Keys travel only in request headers. They are held by the HTTP client and appear in no
attribute, repr, message or log line.
"""

import math
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import numpy as np

from app.backtest.inputs import HistoryInputs
from app.domain.errors import VantageError
from app.domain.research import DailyBar, MarketSnapshot, NewsItem, NewsSnapshot
from app.providers.http import ProviderHttp, ProviderHttpError, RateLimiter, fail
from app.providers.news_common import (
    ERROR_CODE as NEWS_ERROR_CODE,
    MESSAGES as NEWS_MESSAGES,
    build_item,
    build_snapshot,
    upper_symbols,
)
from app.providers.price_validation import (
    RawBar,
    build_market_snapshot,
    validate_context_bars,
)
from app.services.sessions import (
    XNYS,
    latest_completed_xnys_session,
    trailing_xnys_sessions,
)

ALPACA_LIMITER = RateLimiter(150, 60.0)

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
_NEWS_PAGE_SIZE = 50
_NEWS_EXTRA_PAGES = 2
ERROR_CODE = "MARKET_DATA_PROVIDER_FAILED"
SIP_DELAY = timedelta(minutes=16)
ADJUSTMENT_STATE = "split_and_dividend_adjusted"
_MAX_PAGES = 20
_HISTORY_MAX_PAGES = 100  # 51 names x 10 years is about 15 pages of 10,000 bars
HISTORY_BUDGET_SECONDS = 90.0
_NY = ZoneInfo("America/New_York")

_MESSAGES = {
    "auth": "Market data provider refused the configured credentials.",
    "rate_limited": "Market data provider rate limit was reached.",
    "unavailable": "Market prices could not be retrieved.",
    "rejected": "Market data provider refused the request.",
    "not_found": "Market data provider refused the request.",
    "malformed": "Market data provider returned an unreadable response.",
}
_EMPTY_MESSAGE = "No market prices were available for the requested symbol."

_Bars = dict[str, list[dict[str, Any]]]


def _number(value: object, *, allow_zero: bool = False) -> float:
    """A finite positive number from a bar field, else the response is unreadable."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProviderHttpError("malformed")
    number = float(value)
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        raise ProviderHttpError("malformed")
    return number


def _parse_session(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).astimezone(_NY).date()
    except ValueError:
        return None


class AlpacaMarketProvider:
    name: str = "alpaca"

    def __init__(
        self,
        key_id: str,
        secret_key: str,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = ProviderHttp(
            timeout_seconds=timeout_seconds,
            limiter=ALPACA_LIMITER,
            headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key},
            transport=transport,
            sleep=sleep,
        )
        self._now = now

    def __repr__(self) -> str:
        return "AlpacaMarketProvider()"

    def fetch_daily_snapshot(
        self,
        symbol: str,
        start_session: date,
        end_session: date,
        retrieved_at: datetime,
        *,
        context_symbols: tuple[str, ...] = (),
    ) -> MarketSnapshot:
        del start_session  # the window is always the trailing sessions
        primary = symbol.strip().upper()
        symbols = [primary]
        for extra in context_symbols:
            name = extra.strip().upper()
            if name and name not in symbols:
                symbols.append(name)

        session_close = XNYS.session_close(end_session).to_pydatetime().astimezone(UTC)
        end = min(session_close, self._now().astimezone(UTC) - SIP_DELAY)
        effective_end = (
            end_session if end >= session_close else latest_completed_xnys_session(end)
        )
        expected = trailing_xnys_sessions(effective_end)

        try:
            deadline = self._http.deadline()
            raw = self._fetch(symbols, expected[0], end, "raw", deadline)
            adjusted = self._fetch(symbols, expected[0], end, "all", deadline)
        except ProviderHttpError as err:
            raise fail(ERROR_CODE, _MESSAGES, err) from None

        if not raw.get(primary):
            raise VantageError(code=ERROR_CODE, safe_message=_EMPTY_MESSAGE)

        # A bar is stamped at midnight New York time, so the clamped end can still
        # admit the session that has not closed yet; keep only the expected sessions.
        wanted = set(expected)
        primary_bars = self._join(raw, adjusted, primary, wanted)
        if primary_bars is None:
            raise VantageError(code=ERROR_CODE, safe_message=_MESSAGES["malformed"])

        snapshot = build_market_snapshot(
            symbol=primary,
            raw_bars=primary_bars,
            expected_sessions=expected,
            end_session=end_session,
            provider=self.name,
            retrieved_at=retrieved_at,
            adjustment_state=ADJUSTMENT_STATE,
        )

        context: dict[str, list[DailyBar]] = {}
        for name in symbols[1:]:
            joined = self._join(raw, adjusted, name, wanted)
            validated = (
                validate_context_bars(
                    name, joined, self.name, retrieved_at, ADJUSTMENT_STATE
                )
                if joined
                else None
            )
            if validated:
                context[name] = validated
        return snapshot.model_copy(update={"context_bars": context})

    def fetch_daily_history(
        self,
        symbols: tuple[str, ...],
        benchmark: str,
        start: date,
        end: date,
        retrieved_at: datetime,
    ) -> HistoryInputs:
        """Daily history for a simulation: adjusted prices and raw dollar volume.

        Sessions come from the XNYS calendar; a name without a bar on a session is
        NaN there. Gaps, late listings and early ends are judged by the experiment,
        not here, so every caller sees the same rules.
        """
        unique = list(dict.fromkeys((*symbols, benchmark)))
        session_close = XNYS.session_close(end).to_pydatetime().astimezone(UTC)
        clamp = min(session_close, self._now().astimezone(UTC) - SIP_DELAY)
        effective_end = (
            end if clamp >= session_close else latest_completed_xnys_session(clamp)
        )
        grid = [s.date() for s in XNYS.sessions_in_range(start, effective_end)]
        index = {session: i for i, session in enumerate(grid)}
        try:
            deadline = self._http.deadline(HISTORY_BUDGET_SECONDS)
            raw = self._fetch(unique, start, clamp, "raw", deadline, _HISTORY_MAX_PAGES)
            adjusted = self._fetch(
                unique, start, clamp, "all", deadline, _HISTORY_MAX_PAGES
            )
            columns = {
                name: self._history_columns(raw, adjusted, name, index)
                for name in unique
            }
        except ProviderHttpError as err:
            raise fail(ERROR_CODE, _MESSAGES, err) from None
        names = (*symbols, benchmark)
        return HistoryInputs(
            symbols=tuple(symbols),
            benchmark=benchmark,
            sessions=np.array(grid, dtype="datetime64[D]"),
            open_adj=np.column_stack([columns[n][0] for n in names]),
            close_adj=np.column_stack([columns[n][1] for n in names]),
            dollar_volume=np.column_stack([columns[n][2] for n in names]),
            provider=self.name,
            retrieved_at=retrieved_at,
        )

    @staticmethod
    def _history_columns(
        raw: _Bars, adjusted: _Bars, symbol: str, index: dict[date, int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        opens, closes, dollar_volume = (np.full(len(index), np.nan) for _ in range(3))
        for source, is_raw in ((adjusted, False), (raw, True)):
            for bar in source.get(symbol, []):
                if not isinstance(bar, dict):
                    raise ProviderHttpError("malformed")
                session = _parse_session(bar.get("t"))
                if session is None:
                    raise ProviderHttpError("malformed")
                i = index.get(session)
                if i is None:
                    continue
                if is_raw:
                    volume = _number(bar.get("v"), allow_zero=True)
                    dollar_volume[i] = _number(bar.get("c")) * volume
                else:
                    opens[i], closes[i] = _number(bar.get("o")), _number(bar.get("c"))
        return opens, closes, dollar_volume

    def _fetch(
        self,
        symbols: list[str],
        start: date,
        end: datetime,
        adjustment: str,
        deadline: float,
        max_pages: int = _MAX_PAGES,
    ) -> _Bars:
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "feed": "sip",
            "limit": "10000",
            "sort": "asc",
            "start": start.isoformat(),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "adjustment": adjustment,
        }
        merged: _Bars = {}
        for _ in range(max_pages):
            payload = self._http.get_json(BARS_URL, params=params, deadline=deadline)
            if not isinstance(payload, dict):
                raise ProviderHttpError("malformed")
            page = payload.get("bars") or {}
            if not isinstance(page, dict):
                raise ProviderHttpError("malformed")
            for sym, bars in page.items():
                if bars is None:
                    continue
                if not isinstance(bars, list):
                    raise ProviderHttpError("malformed")
                merged.setdefault(str(sym).upper(), []).extend(bars)
            token = payload.get("next_page_token")
            if not token:
                return merged
            if not isinstance(token, str):
                raise ProviderHttpError("malformed")
            params = {**params, "page_token": token}
        raise ProviderHttpError("malformed")

    @staticmethod
    def _join(
        raw: _Bars, adjusted: _Bars, symbol: str, sessions: set[date]
    ) -> list[RawBar] | None:
        """Join raw and adjusted bars on New York date; None when a bar is unreadable.

        Only expected sessions are kept. A date present in only one response is a
        missing session and is dropped.
        """
        adjusted_close: dict[date, object] = {}
        for bar in adjusted.get(symbol, []):
            if not isinstance(bar, dict):
                return None
            session = _parse_session(bar.get("t"))
            if session is None:
                return None
            adjusted_close[session] = bar.get("c")

        joined: list[RawBar] = []
        for bar in raw.get(symbol, []):
            if not isinstance(bar, dict):
                return None
            session = _parse_session(bar.get("t"))
            if session is None:
                return None
            if session not in adjusted_close or session not in sessions:
                continue
            joined.append(
                RawBar(
                    session_date=session,
                    open=bar.get("o"),
                    high=bar.get("h"),
                    low=bar.get("l"),
                    close=bar.get("c"),
                    adjusted_close=adjusted_close[session],
                    volume=bar.get("v"),
                )
            )
        return joined


class AlpacaNewsProvider:
    """Alpaca company news. Shares the Alpaca rate limiter with the market provider."""

    name: str = "alpaca"

    def __init__(
        self,
        key_id: str,
        secret_key: str,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = ProviderHttp(
            timeout_seconds=timeout_seconds,
            limiter=ALPACA_LIMITER,
            headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key},
            transport=transport,
            sleep=sleep,
        )

    def __repr__(self) -> str:
        return "AlpacaNewsProvider()"

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
        retrieved_utc = retrieved_at.astimezone(UTC)
        params = {
            "symbols": primary,
            "start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": cutoff_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": str(_NEWS_PAGE_SIZE),
            "sort": "desc",
            "include_content": "false",
        }
        try:
            deadline = self._http.deadline()
            raw_items = self._fetch_pages(params, deadline)
        except ProviderHttpError as err:
            raise fail(NEWS_ERROR_CODE, NEWS_MESSAGES, err) from None

        items: list[NewsItem] = []
        for raw in raw_items:
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

    def _fetch_pages(self, params: dict[str, str], deadline: float) -> list[Any]:
        collected: list[Any] = []
        for _ in range(1 + _NEWS_EXTRA_PAGES):
            payload = self._http.get_json(NEWS_URL, params=params, deadline=deadline)
            if not isinstance(payload, dict):
                raise ProviderHttpError("malformed")
            page = payload.get("news")
            if page is None:
                page = []
            if not isinstance(page, list):
                raise ProviderHttpError("malformed")
            collected.extend(page)
            token = payload.get("next_page_token")
            if not token:
                break
            if not isinstance(token, str):
                raise ProviderHttpError("malformed")
            params = {**params, "page_token": token}
        return collected

    def _item(self, raw: object, retrieved_at: datetime) -> NewsItem | None:
        if not isinstance(raw, dict):
            return None
        created = raw.get("created_at")
        if not isinstance(created, str):
            return None
        try:
            event_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            return None
        if event_time.tzinfo is None:
            return None
        symbols = raw.get("symbols")
        return build_item(
            provider=self.name,
            raw_id=raw.get("id"),
            publisher=raw.get("source"),
            title=raw.get("headline"),
            summary=raw.get("summary"),
            url=raw.get("url"),
            event_time=event_time.astimezone(UTC),
            symbols=upper_symbols(symbols) if isinstance(symbols, list) else [],
            retrieved_at=retrieved_at,
        )
