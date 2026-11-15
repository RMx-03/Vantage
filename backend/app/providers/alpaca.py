"""Alpaca SIP daily-bar market provider.

Alpaca's free plan serves SIP data only after a 15-minute delay, so the request end is
clamped to ``now - 16 minutes``. When the clamp lands before the session close, the
snapshot is built for the latest session that has closed by then and is reported as
``STALE`` against the requested session, never padded or relabelled.

Keys travel only in request headers. They are held by the HTTP client and appear in no
attribute, repr, message or log line.
"""

import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.domain.errors import VantageError
from app.domain.research import DailyBar, MarketSnapshot
from app.providers.http import ProviderHttp, ProviderHttpError, RateLimiter, fail
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
ERROR_CODE = "MARKET_DATA_PROVIDER_FAILED"
SIP_DELAY = timedelta(minutes=16)
ADJUSTMENT_STATE = "split_and_dividend_adjusted"
_MAX_PAGES = 20
_NY = ZoneInfo("America/New_York")

_MESSAGES = {
    "auth": "Market data provider rejected the configured credentials.",
    "rate_limited": "Market data provider rate limit was reached.",
    "unavailable": "Market prices could not be retrieved.",
    "rejected": "Market data provider rejected the request.",
    "not_found": "Market data provider rejected the request.",
    "malformed": "Market data provider returned an unreadable response.",
}
_EMPTY_MESSAGE = "No market prices were available for the requested symbol."

_Bars = dict[str, list[dict[str, Any]]]


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

    def _fetch(
        self,
        symbols: list[str],
        start: date,
        end: datetime,
        adjustment: str,
        deadline: float,
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
        for _ in range(_MAX_PAGES):
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
