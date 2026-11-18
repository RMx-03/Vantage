import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import ComponentQuality
from app.providers.cache import InMemoryProviderCache
from app.providers.fred import FRED_LIMITER, MACRO_SERIES, FredMacroProvider
from app.providers.registry import build_providers

PROVIDER_ENV = (
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET_KEY",
    "FINNHUB_API_KEY",
    "FRED_API_KEY",
    "TIINGO_API_KEY",
    "SEC_USER_AGENT",
    "MARKET_PROVIDER",
    "NEWS_PROVIDERS",
    "FILINGS_PROVIDER",
    "MACRO_PROVIDER",
    "PRICE_CROSSCHECK_PROVIDER",
)

KEY = "fred-test-key-QWERTY1234567890"
URL = "https://api.stlouisfed.org/fred/series/observations"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "providers" / "fred"
END = date(2026, 11, 13)
RETRIEVED = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)

BODIES = {
    "DFF": json.loads((FIXTURES / "dff.json").read_text()),
    "DGS10": json.loads((FIXTURES / "dgs10.json").read_text()),
    "T10Y2Y": json.loads((FIXTURES / "t10y2y.json").read_text()),
    "VIXCLS": json.loads((FIXTURES / "vixcls.json").read_text()),
}
HOLIDAY = json.loads((FIXTURES / "holiday.json").read_text())

MESSAGES = {
    "auth": "FRED refused the configured API key.",
    "rate_limited": "FRED rate limit was reached.",
    "other": "Macro series could not be retrieved.",
}


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    FRED_LIMITER._calls.clear()


def make_provider(
    cache: Any = None, transport: httpx.BaseTransport | None = None
) -> FredMacroProvider:
    return FredMacroProvider(
        KEY,
        cache if cache is not None else InMemoryProviderCache(),
        timeout_seconds=6.0,
        transport=transport,
        sleep=lambda seconds: None,
    )


def by_series(handler: Callable[[str], httpx.Response]) -> respx.Route:
    def side_effect(request: httpx.Request) -> httpx.Response:
        return handler(request.url.params["series_id"])

    return respx.get(URL).mock(side_effect=side_effect)


def ok(series_id: str) -> httpx.Response:
    return httpx.Response(200, json=BODIES[series_id])


def one_row(date_text: str, value: str = "3.9") -> dict[str, Any]:
    return {"observations": [{"date": date_text, "value": value}]}


def _chain_text(error: BaseException | None) -> str:
    parts = []
    while error is not None:
        parts.append(repr(error))
        parts.append(str(error))
        error = error.__cause__ or error.__context__
    return " ".join(parts)


@respx.mock
def test_happy_path_returns_four_sorted_fresh_observations() -> None:
    route = by_series(ok)

    snapshot = make_provider().fetch_macro(END, RETRIEVED)

    assert MACRO_SERIES == ("DFF", "DGS10", "T10Y2Y", "VIXCLS")
    assert snapshot.provider == "fred"
    assert snapshot.quality is ComponentQuality.FRESH
    assert snapshot.error_code is None
    assert snapshot.retrieved_at == RETRIEVED
    assert [o.series_id for o in snapshot.observations] == list(MACRO_SERIES)
    values = {o.series_id: o.value for o in snapshot.observations}
    assert values == {"DFF": 3.91, "DGS10": 4.12, "T10Y2Y": 0.52, "VIXCLS": 16.21}
    assert all(o.observation_date == END for o in snapshot.observations)
    assert all(o.quality is ComponentQuality.FRESH for o in snapshot.observations)
    assert route.call_count == 4
    params = route.calls[0].request.url.params
    assert params["file_type"] == "json"
    assert params["observation_end"] == "2026-11-13"
    assert params["sort_order"] == "desc"
    assert params["limit"] == "10"
    assert params["api_key"] == KEY


@respx.mock
def test_dot_rows_are_skipped_to_the_latest_real_value() -> None:
    body = {
        "observations": [
            {"date": "2026-11-13", "value": "."},
            {"date": "2026-11-12", "value": "4.09"},
        ]
    }
    by_series(lambda s: httpx.Response(200, json=body))

    snapshot = make_provider().fetch_macro(END, RETRIEVED)

    assert all(o.value == 4.09 for o in snapshot.observations)
    assert all(o.observation_date == date(2026, 11, 12) for o in snapshot.observations)


@respx.mock
def test_non_finite_and_unparseable_values_are_skipped() -> None:
    body = {
        "observations": [
            {"date": "2026-11-13", "value": "nan"},
            {"date": "2026-11-12", "value": "inf"},
            {"date": "2026-11-11", "value": "abc"},
            {"date": "2026-11-10", "value": "4.07"},
        ]
    }
    by_series(lambda s: httpx.Response(200, json=body))

    snapshot = make_provider().fetch_macro(END, RETRIEVED)

    assert all(o.value == 4.07 for o in snapshot.observations)
    assert all(o.observation_date == date(2026, 11, 10) for o in snapshot.observations)


@respx.mock
def test_observation_on_the_window_edge_is_fresh_and_one_day_older_is_stale() -> None:
    def handler(series_id: str) -> httpx.Response:
        if series_id == "DFF":
            return httpx.Response(200, json=one_row("2026-11-06"))
        if series_id == "DGS10":
            return httpx.Response(200, json=one_row("2026-11-05", "4.1"))
        return ok(series_id)

    by_series(handler)

    snapshot = make_provider().fetch_macro(END, RETRIEVED)

    quality = {o.series_id: o.quality for o in snapshot.observations}
    assert quality["DFF"] is ComponentQuality.FRESH
    assert quality["DGS10"] is ComponentQuality.STALE
    assert snapshot.quality is ComponentQuality.STALE
    assert snapshot.error_code is None


@respx.mock
def test_all_dot_rows_give_a_missing_observation_and_partial_snapshot() -> None:
    def handler(series_id: str) -> httpx.Response:
        if series_id == "VIXCLS":
            return httpx.Response(200, json=HOLIDAY)
        return ok(series_id)

    by_series(handler)

    snapshot = make_provider().fetch_macro(END, RETRIEVED)

    vix = next(o for o in snapshot.observations if o.series_id == "VIXCLS")
    assert vix.value is None
    assert vix.observation_date is None
    assert vix.quality is ComponentQuality.MISSING
    assert snapshot.quality is ComponentQuality.PARTIAL


@respx.mock
def test_stale_outranks_missing_in_the_snapshot_quality() -> None:
    def handler(series_id: str) -> httpx.Response:
        if series_id == "VIXCLS":
            return httpx.Response(200, json=HOLIDAY)
        if series_id == "DFF":
            return httpx.Response(200, json=one_row("2026-11-05"))
        return ok(series_id)

    by_series(handler)

    snapshot = make_provider().fetch_macro(END, RETRIEVED)

    assert snapshot.quality is ComponentQuality.STALE


@respx.mock
def test_second_call_is_served_from_the_cache() -> None:
    route = by_series(ok)
    cache = InMemoryProviderCache()
    provider = make_provider(cache)

    first = provider.fetch_macro(END, RETRIEVED)
    second = provider.fetch_macro(END, RETRIEVED)

    assert route.call_count == 4
    assert second.observations == first.observations
    entry = cache.get("fred", "fred:DGS10", END)
    assert entry is not None
    assert entry.payload == {"value": 4.12, "observation_date": "2026-11-13"}


@respx.mock
def test_stale_and_missing_observations_are_not_cached() -> None:
    def handler(series_id: str) -> httpx.Response:
        if series_id == "VIXCLS":
            return httpx.Response(200, json=HOLIDAY)
        if series_id == "DFF":
            return httpx.Response(200, json=one_row("2026-11-05"))
        return ok(series_id)

    route = by_series(handler)
    cache = InMemoryProviderCache()
    provider = make_provider(cache)

    provider.fetch_macro(END, RETRIEVED)
    assert cache.get("fred", "fred:DFF", END) is None
    assert cache.get("fred", "fred:VIXCLS", END) is None
    assert cache.get("fred", "fred:DGS10", END) is not None

    provider.fetch_macro(END, RETRIEVED)
    # Only the two uncached series are requested again.
    assert route.call_count == 4 + 2


@respx.mock
def test_cached_series_is_not_requested_again() -> None:
    route = by_series(ok)
    cache = InMemoryProviderCache()
    cache.put(
        "fred",
        "fred:DFF",
        END,
        {"value": 3.9, "observation_date": "2026-11-12"},
        RETRIEVED,
    )

    snapshot = make_provider(cache).fetch_macro(END, RETRIEVED)

    assert route.call_count == 3
    dff = next(o for o in snapshot.observations if o.series_id == "DFF")
    assert dff.value == 3.9
    assert dff.observation_date == date(2026, 11, 12)
    assert dff.quality is ComponentQuality.FRESH


@respx.mock
def test_malformed_cache_payload_is_a_miss() -> None:
    route = by_series(ok)
    cache = InMemoryProviderCache()
    cache.put("fred", "fred:DFF", END, {"value": "x"}, RETRIEVED)

    snapshot = make_provider(cache).fetch_macro(END, RETRIEVED)

    assert route.call_count == 4
    assert snapshot.quality is ComponentQuality.FRESH


class BrokenCache:
    def get(self, provider: str, cache_key: str, valid_for_date: date) -> Any:
        raise SQLAlchemyError("db password=hunter2 select")

    def put(self, *args: Any, **kwargs: Any) -> Any:
        raise SQLAlchemyError("db password=hunter2 insert")


@respx.mock
def test_cache_failure_never_fails_the_role(caplog: pytest.LogCaptureFixture) -> None:
    by_series(ok)

    with caplog.at_level(logging.DEBUG):
        snapshot = make_provider(BrokenCache()).fetch_macro(END, RETRIEVED)

    assert snapshot.quality is ComponentQuality.FRESH
    assert "provider_cache_unavailable" in caplog.text
    assert "hunter2" not in caplog.text
    assert KEY not in caplog.text


@respx.mock
def test_status_400_is_rejected_with_the_generic_message() -> None:
    by_series(lambda s: httpx.Response(400, text="Bad Request"))

    with pytest.raises(VantageError) as exc:
        make_provider().fetch_macro(END, RETRIEVED)

    assert exc.value.code == "MACRO_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["other"]


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_has_its_own_message(status: int) -> None:
    by_series(lambda s: httpx.Response(status))

    with pytest.raises(VantageError) as exc:
        make_provider().fetch_macro(END, RETRIEVED)

    assert exc.value.code == "MACRO_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["auth"]


@respx.mock
def test_429_retries_once_then_fails_with_the_rate_limit_message() -> None:
    route = by_series(lambda s: httpx.Response(429))

    with pytest.raises(VantageError) as exc:
        make_provider().fetch_macro(END, RETRIEVED)

    assert exc.value.code == "MACRO_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["rate_limited"]
    assert exc.value.retryable is True
    assert route.call_count == 2


@respx.mock
def test_500_retries_once_then_fails_with_the_generic_message() -> None:
    route = by_series(lambda s: httpx.Response(500))

    with pytest.raises(VantageError) as exc:
        make_provider().fetch_macro(END, RETRIEVED)

    assert exc.value.safe_message == MESSAGES["other"]
    assert route.call_count == 2


@respx.mock
def test_retry_succeeds_after_one_429() -> None:
    state = {"n": 0}

    def handler(series_id: str) -> httpx.Response:
        if series_id == "DFF" and state["n"] == 0:
            state["n"] += 1
            return httpx.Response(429)
        return ok(series_id)

    by_series(handler)

    snapshot = make_provider().fetch_macro(END, RETRIEVED)

    assert snapshot.quality is ComponentQuality.FRESH


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json={"observations": "nope"}),
    ],
)
def test_malformed_body_raises(response: httpx.Response) -> None:
    by_series(lambda s: response)

    with pytest.raises(VantageError) as exc:
        make_provider().fetch_macro(END, RETRIEVED)

    assert exc.value.code == "MACRO_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["other"]


@respx.mock
def test_junk_rows_are_ignored() -> None:
    body = {
        "observations": [
            "junk",
            {"date": 5, "value": "1"},
            {"date": "not-a-date", "value": "1"},
            {"date": "2026-11-13", "value": 4.1},
            {"date": "2026-11-12", "value": "4.09"},
        ]
    }
    by_series(lambda s: httpx.Response(200, json=body))

    snapshot = make_provider().fetch_macro(END, RETRIEVED)

    assert all(o.value == 4.09 for o in snapshot.observations)


@respx.mock
def test_all_series_requests_share_one_deadline() -> None:
    now = {"t": 0.0}

    def handler(series_id: str) -> httpx.Response:
        now["t"] += 2.0
        return ok(series_id)

    by_series(handler)
    provider = make_provider()
    provider._http._clock = lambda: now["t"]

    with pytest.raises(VantageError) as exc:
        provider.fetch_macro(END, RETRIEVED)

    # Four 2 s requests cannot fit one 6 s budget.
    assert exc.value.code == "MACRO_PROVIDER_FAILED"


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_api_key_never_leaks(status: int, caplog: pytest.LogCaptureFixture) -> None:
    by_series(lambda s: httpx.Response(status, text=f"api_key={KEY}"))
    provider = make_provider()

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(VantageError) as exc:
            provider.fetch_macro(END, RETRIEVED)

    assert exc.value.__cause__ is None
    for text in (_chain_text(exc.value), repr(provider), caplog.text):
        assert KEY not in text
        assert "api_key" not in text


@respx.mock
def test_connect_error_does_not_leak_the_url() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError(f"boom {URL}?api_key={KEY}"))

    with pytest.raises(VantageError) as exc:
        make_provider().fetch_macro(END, RETRIEVED)

    assert exc.value.safe_message == MESSAGES["other"]
    assert KEY not in _chain_text(exc.value)
    assert URL not in _chain_text(exc.value)


@respx.mock
def test_key_is_absent_from_cached_payloads() -> None:
    by_series(ok)
    cache = InMemoryProviderCache()

    make_provider(cache).fetch_macro(END, RETRIEVED)

    payloads = [e.payload for e in cache._entries.values()]
    assert len(payloads) == 4
    assert all(set(p) == {"value", "observation_date"} for p in payloads)
    dumped = json.dumps(payloads)
    assert KEY not in dumped
    assert "api_key" not in dumped


def test_repr_is_fixed() -> None:
    assert repr(make_provider()) == "FredMacroProvider()"


def test_registry_builds_fred_only_with_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    keyed = build_providers(
        Settings(_env_file=None, MACRO_PROVIDER="fred", FRED_API_KEY="k")
    )
    assert keyed.macro is not None and keyed.macro.name == "fred"
    assert "macro" not in keyed.not_configured

    missing = build_providers(Settings(_env_file=None, MACRO_PROVIDER="fred"))
    assert missing.macro is None
    assert "macro" in missing.not_configured

    default = build_providers(Settings(_env_file=None))
    assert default.macro is None
