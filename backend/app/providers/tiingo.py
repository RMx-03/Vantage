"""Tiingo adjusted-close cross-check provider.

The key travels only in the ``Authorization`` header. It is held by the HTTP client and
appears in no attribute, repr, message or log line. The limiter refuses instead of
waiting, so an exhausted hourly allowance fails the role without a request.
"""

import math
import time
from collections.abc import Callable
from datetime import date, datetime

import httpx

from app.domain.research import (
    ComponentQuality,
    CrossCheckClose,
    PriceCrossCheckSnapshot,
)
from app.providers.http import ProviderHttp, ProviderHttpError, RateLimiter, fail

TIINGO_LIMITER = RateLimiter(40, 3600.0, max_wait_seconds=0)

PRICES_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"

ERROR_CODE = "PRICE_CROSSCHECK_FAILED"
UNAVAILABLE_CODE = "PRICE_CROSSCHECK_UNAVAILABLE"
MESSAGES = {
    "auth": "Tiingo refused the configured API key.",
    "rate_limited": "Tiingo rate limit was reached.",
    "unavailable": "Cross-check prices could not be retrieved.",
    "rejected": "Cross-check prices could not be retrieved.",
    "not_found": "Cross-check prices could not be retrieved.",
    "malformed": "Cross-check prices could not be retrieved.",
}


def _close(raw: object) -> CrossCheckClose | None:
    if not isinstance(raw, dict):
        return None
    stamp, value = raw.get("date"), raw.get("adjClose")
    if not isinstance(stamp, str):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    try:
        session = date.fromisoformat(stamp[:10])
    except ValueError:
        return None
    return CrossCheckClose(session_date=session, adjusted_close=float(value))


class TiingoCrossCheckProvider:
    name: str = "tiingo"

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
            limiter=TIINGO_LIMITER,
            headers={"Authorization": f"Token {api_key}"},
            transport=transport,
            sleep=sleep,
        )

    def __repr__(self) -> str:
        return "TiingoCrossCheckProvider()"

    def fetch_adjusted_closes(
        self,
        symbol: str,
        start_session: date,
        end_session: date,
        retrieved_at: datetime,
    ) -> PriceCrossCheckSnapshot:
        primary = symbol.strip().upper()
        url = PRICES_URL.format(symbol=primary.replace(".", "-"))
        params = {
            "startDate": start_session.isoformat(),
            "endDate": end_session.isoformat(),
        }
        payload: object = []
        try:
            deadline = self._http.deadline()
            payload = self._http.get_json(url, params=params, deadline=deadline)
            if not isinstance(payload, list):
                raise ProviderHttpError("malformed")
        except ProviderHttpError as err:
            if err.kind != "not_found":
                raise fail(ERROR_CODE, MESSAGES, err) from None
            payload = []

        closes: dict[date, CrossCheckClose] = {}
        for raw in payload if isinstance(payload, list) else []:
            close = _close(raw)
            if close is not None:
                closes[close.session_date] = close
        ordered = [closes[day] for day in sorted(closes)]
        if not ordered:
            return PriceCrossCheckSnapshot(
                symbol=primary,
                provider=self.name,
                retrieved_at=retrieved_at,
                quality=ComponentQuality.MISSING,
                error_code=UNAVAILABLE_CODE,
            )
        return PriceCrossCheckSnapshot(
            symbol=primary,
            provider=self.name,
            retrieved_at=retrieved_at,
            quality=ComponentQuality.FRESH,
            closes=ordered,
        )
