"""FRED macro-level provider.

FRED takes its key only as the ``api_key`` query parameter. The key is held privately
and sent only as that query parameter; it never appears in an error, repr, cache
payload or log line, and the ``httpx`` logger is held at WARNING so request URLs are
never logged.
"""

import math
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import httpx

from app.domain.research import ComponentQuality, MacroObservation, MacroSnapshot
from app.providers.cache import ProviderCache, cache_get_safely, cache_put_safely
from app.providers.http import ProviderHttp, ProviderHttpError, RateLimiter, fail
from app.services.sessions import trailing_xnys_sessions

FRED_LIMITER = RateLimiter(100, 60.0)

OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
MACRO_SERIES = ("DFF", "DGS10", "T10Y2Y", "VIXCLS")
FRESH_WINDOW_SESSIONS = 6
OBSERVATION_LIMIT = 10

ERROR_CODE = "MACRO_PROVIDER_FAILED"
MESSAGES = {
    "auth": "FRED refused the configured API key.",
    "rate_limited": "FRED rate limit was reached.",
    "unavailable": "Macro series could not be retrieved.",
    "rejected": "Macro series could not be retrieved.",
    "not_found": "Macro series could not be retrieved.",
    "malformed": "Macro series could not be retrieved.",
}


def _latest_value(payload: Any) -> tuple[float, date] | None:
    """The newest row with a real, finite value, or None when there is none."""
    if not isinstance(payload, dict):
        raise ProviderHttpError("malformed")
    rows = payload.get("observations")
    if not isinstance(rows, list):
        raise ProviderHttpError("malformed")
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_value, raw_date = row.get("value"), row.get("date")
        if not isinstance(raw_value, str) or not isinstance(raw_date, str):
            continue
        if raw_value.strip() == ".":
            continue
        try:
            value = float(raw_value)
            observed = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if not math.isfinite(value):
            continue
        return value, observed
    return None


def _from_cache(payload: Any) -> tuple[float, date] | None:
    if not isinstance(payload, dict):
        return None
    value, raw_date = payload.get("value"), payload.get("observation_date")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isinstance(raw_date, str) or not math.isfinite(value):
        return None
    try:
        return float(value), date.fromisoformat(raw_date)
    except ValueError:
        return None


class FredMacroProvider:
    name: str = "fred"

    def __init__(
        self,
        api_key: str,
        cache: ProviderCache,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._cache = cache
        self._http = ProviderHttp(
            timeout_seconds=timeout_seconds,
            limiter=FRED_LIMITER,
            transport=transport,
            sleep=sleep,
        )

    def __repr__(self) -> str:
        return "FredMacroProvider()"

    def fetch_macro(self, end_session: date, retrieved_at: datetime) -> MacroSnapshot:
        oldest_fresh = trailing_xnys_sessions(end_session, FRESH_WINDOW_SESSIONS)[0]
        observations: list[MacroObservation] = []
        try:
            deadline = self._http.deadline()
            for series_id in MACRO_SERIES:
                observations.append(
                    self._observation(
                        series_id, end_session, oldest_fresh, retrieved_at, deadline
                    )
                )
        except ProviderHttpError as err:
            raise fail(ERROR_CODE, MESSAGES, err) from None

        observations.sort(key=lambda o: o.series_id)
        qualities = {o.quality for o in observations}
        if ComponentQuality.STALE in qualities:
            quality = ComponentQuality.STALE
        elif ComponentQuality.MISSING in qualities:
            quality = ComponentQuality.PARTIAL
        else:
            quality = ComponentQuality.FRESH
        return MacroSnapshot(
            provider=self.name,
            retrieved_at=retrieved_at,
            quality=quality,
            observations=observations,
        )

    def _observation(
        self,
        series_id: str,
        end_session: date,
        oldest_fresh: date,
        retrieved_at: datetime,
        deadline: float,
    ) -> MacroObservation:
        key = f"fred:{series_id}"
        entry = cache_get_safely(self._cache, self.name, key, end_session)
        found = _from_cache(entry.payload) if entry is not None else None
        if found is None:
            params = {
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "observation_end": end_session.isoformat(),
                "sort_order": "desc",
                "limit": str(OBSERVATION_LIMIT),
            }
            payload = self._http.get_json(
                OBSERVATIONS_URL, params=params, deadline=deadline
            )
            found = _latest_value(payload)
            if found is not None and found[1] >= oldest_fresh:
                # Only fresh values are pinned; a late publication must be re-fetched.
                cache_put_safely(
                    self._cache,
                    self.name,
                    key,
                    end_session,
                    {"value": found[0], "observation_date": found[1].isoformat()},
                    retrieved_at,
                )
        if found is None:
            return MacroObservation(
                series_id=series_id,
                value=None,
                observation_date=None,
                quality=ComponentQuality.MISSING,
            )
        value, observed = found
        return MacroObservation(
            series_id=series_id,
            value=value,
            observation_date=observed,
            quality=(
                ComponentQuality.FRESH
                if observed >= oldest_fresh
                else ComponentQuality.STALE
            ),
        )
