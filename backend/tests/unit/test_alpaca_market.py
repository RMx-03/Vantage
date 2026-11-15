import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import ComponentQuality
from app.providers.alpaca import ALPACA_LIMITER, AlpacaMarketProvider
from app.providers.registry import build_providers, default_registry
from app.services.sessions import trailing_xnys_sessions

KEY_ID = "PKTESTKEYID123456"
SECRET = "test-secret-ZXCVBNM987654321"
URL = "https://data.alpaca.markets/v2/stocks/bars"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "providers" / "alpaca"
END_SESSION = date(2026, 11, 13)
NOW_AFTER_CLOSE = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
NOW_DURING_LAG = datetime(2026, 11, 13, 21, 10, tzinfo=UTC)
NY = ZoneInfo("America/New_York")

MESSAGES = {
    "auth": "Market data provider rejected the configured credentials.",
    "rate_limited": "Market data provider rate limit was reached.",
    "unavailable": "Market prices could not be retrieved.",
    "malformed": "Market data provider returned an unreadable response.",
}
EMPTY_MESSAGE = "No market prices were available for the requested symbol."

RAW = json.loads((FIXTURES / "bars_raw.json").read_text())["bars"]
ALL = json.loads((FIXTURES / "bars_all.json").read_text())["bars"]


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    ALPACA_LIMITER._calls.clear()


def _utc(t: str) -> datetime:
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def _select(request: httpx.Request) -> dict[str, list[dict[str, Any]]]:
    """Return the fixture bars inside [start, end], as the real API does."""
    params = request.url.params
    source = ALL if params["adjustment"] == "all" else RAW
    start = date.fromisoformat(params["start"][:10])
    end = _utc(params["end"])
    return {
        sym: [
            dict(bar)
            for bar in source[sym]
            if _utc(bar["t"]).astimezone(NY).date() >= start and _utc(bar["t"]) <= end
        ]
        for sym in params["symbols"].split(",")
        if sym in source
    }


class Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200, json={"bars": _select(request), "next_page_token": None}
        )


def make_provider(
    now: datetime = NOW_AFTER_CLOSE, transport: httpx.BaseTransport | None = None
) -> AlpacaMarketProvider:
    return AlpacaMarketProvider(
        KEY_ID,
        SECRET,
        timeout_seconds=6.0,
        transport=transport,
        now=lambda: now,
        sleep=lambda seconds: None,
    )


def fetch(
    provider: AlpacaMarketProvider,
    symbol: str = "AAPL",
    context: tuple[str, ...] = ("SPY", "XLK"),
) -> Any:
    sessions = trailing_xnys_sessions(END_SESSION)
    return provider.fetch_daily_snapshot(
        symbol,
        sessions[0],
        END_SESSION,
        NOW_AFTER_CLOSE,
        context_symbols=context,
    )


def route(handler: Callable[[httpx.Request], httpx.Response]) -> respx.Route:
    return respx.get(URL).mock(side_effect=handler)


@respx.mock
def test_happy_path_joins_raw_and_adjusted_bars() -> None:
    recorder = Recorder()
    route(recorder)

    snapshot = fetch(make_provider())

    assert snapshot.provider == "alpaca"
    assert snapshot.quality is ComponentQuality.FRESH
    assert len(snapshot.bars) == 21
    assert [b.session_date for b in snapshot.bars] == list(
        trailing_xnys_sessions(END_SESSION)
    )
    last = snapshot.bars[-1]
    assert last.session_date == END_SESSION
    assert last.close == RAW["AAPL"][-1]["c"]
    assert last.adjusted_close == ALL["AAPL"][-1]["c"]
    assert last.volume == RAW["AAPL"][-1]["v"]
    assert last.adjustment_state == "split_and_dividend_adjusted"
    first = snapshot.bars[0]
    assert first.adjusted_close < first.close
    assert set(snapshot.context_bars) == {"SPY", "XLK"}
    assert all(len(bars) == 21 for bars in snapshot.context_bars.values())

    assert len(recorder.requests) == 2
    assert {r.url.params["adjustment"] for r in recorder.requests} == {"raw", "all"}
    for request in recorder.requests:
        params = request.url.params
        assert params["symbols"] == "AAPL,SPY,XLK"
        assert params["timeframe"] == "1Day"
        assert params["feed"] == "sip"
        assert params["limit"] == "10000"
        assert params["sort"] == "asc"
        assert params["start"] == "2026-10-16"
        assert params["end"] == "2026-11-13T21:00:00Z"


@respx.mock
def test_end_is_clamped_to_sixteen_minutes_before_now() -> None:
    recorder = Recorder()
    route(recorder)

    snapshot = fetch(make_provider(NOW_DURING_LAG))

    assert {r.url.params["end"] for r in recorder.requests} == {"2026-11-13T20:54:00Z"}
    assert recorder.requests[0].url.params["start"] == "2026-10-15"
    assert snapshot.bars[-1].session_date == date(2026, 11, 12)
    assert len(snapshot.bars) == 21
    assert snapshot.quality is ComponentQuality.STALE


@respx.mock
def test_pagination_merges_pages() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("page_token")
        seen.append(token)
        bars = _select(request)
        if token is None:
            first = {s: b[:10] for s, b in bars.items()}
            return httpx.Response(200, json={"bars": first, "next_page_token": "p2"})
        assert token == "p2"
        rest = {s: b[10:] for s, b in bars.items()}
        return httpx.Response(200, json={"bars": rest, "next_page_token": None})

    route(handler)

    snapshot = fetch(make_provider())

    assert len(snapshot.bars) == 21
    assert seen.count("p2") == 2
    assert seen.count(None) == 2


@respx.mock
def test_empty_bars_object_is_empty_series_error() -> None:
    route(lambda r: httpx.Response(200, json={"bars": {}, "next_page_token": None}))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "MARKET_DATA_PROVIDER_FAILED"
    assert exc.value.safe_message == EMPTY_MESSAGE


@respx.mock
@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "auth"),
        (403, "auth"),
        (429, "rate_limited"),
        (500, "unavailable"),
    ],
)
def test_http_failures_map_to_fixed_messages(status: int, kind: str) -> None:
    route(lambda r: httpx.Response(status, text=f"{KEY_ID} {SECRET}"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "MARKET_DATA_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES[kind]
    assert exc.value.retryable is (kind in {"rate_limited", "unavailable"})


@respx.mock
def test_rejected_request_message() -> None:
    route(lambda r: httpx.Response(422, text="bad"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == "Market data provider rejected the request."


@respx.mock
def test_malformed_body_message() -> None:
    route(lambda r: httpx.Response(200, text="<html>not json</html>"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
def test_unexpected_json_shape_is_malformed() -> None:
    route(lambda r: httpx.Response(200, json=["nope"]))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
def test_unparseable_bar_timestamp_is_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        bars = _select(request)
        bars["AAPL"][3]["t"] = "yesterday"
        return httpx.Response(200, json={"bars": bars, "next_page_token": None})

    route(handler)

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
def test_session_missing_from_adjusted_response_is_a_missing_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        bars = _select(request)
        if request.url.params["adjustment"] == "all":
            bars["AAPL"] = bars["AAPL"][:-1]
        return httpx.Response(200, json={"bars": bars, "next_page_token": None})

    route(handler)

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "INVALID_PRICE_SERIES"


@respx.mock
def test_invalid_context_symbol_is_dropped_and_primary_passes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        bars = _select(request)
        if request.url.params["adjustment"] == "raw":
            bars["SPY"][5]["c"] = 0
        return httpx.Response(200, json={"bars": bars, "next_page_token": None})

    route(handler)

    snapshot = fetch(make_provider())

    assert len(snapshot.bars) == 21
    assert set(snapshot.context_bars) == {"XLK"}


@respx.mock
def test_context_symbol_without_bars_is_left_out() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        bars = _select(request)
        bars.pop("XLK")
        return httpx.Response(200, json={"bars": bars, "next_page_token": None})

    route(handler)

    snapshot = fetch(make_provider())

    assert set(snapshot.context_bars) == {"SPY"}


def test_transport_receives_key_headers_and_no_key_in_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"bars": _select(request), "next_page_token": None}
        )

    fetch(make_provider(transport=httpx.MockTransport(handler)))

    assert seen
    for request in seen:
        assert request.headers["APCA-API-KEY-ID"] == KEY_ID
        assert request.headers["APCA-API-SECRET-KEY"] == SECRET
        assert KEY_ID not in str(request.url)
        assert SECRET not in str(request.url)


def _chain_text(error: BaseException | None) -> str:
    parts: list[str] = []
    while error is not None:
        parts.append(repr(error))
        parts.append(str(error))
        error = error.__cause__ or error.__context__
    return " ".join(parts)


@respx.mock
@pytest.mark.parametrize("status", [401, 429, 500])
def test_keys_never_leak(status: int, caplog: pytest.LogCaptureFixture) -> None:
    route(lambda r: httpx.Response(status, text=f"{KEY_ID} {SECRET}"))
    provider = make_provider()

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(VantageError) as exc:
            fetch(provider)

    assert exc.value.__cause__ is None
    for text in (_chain_text(exc.value), repr(provider), caplog.text):
        assert KEY_ID not in text
        assert SECRET not in text


@respx.mock
def test_connect_error_does_not_leak_into_the_chain() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError(f"boom {URL}?k={SECRET}"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["unavailable"]
    assert SECRET not in _chain_text(exc.value)
    assert URL not in _chain_text(exc.value)


@respx.mock
def test_primary_is_not_requested_twice_when_listed_as_context() -> None:
    recorder = Recorder()
    route(recorder)

    fetch(make_provider(), context=("aapl", "spy"))

    assert recorder.requests[0].url.params["symbols"] == "AAPL,SPY"


def test_registry_builds_provider_with_both_keys() -> None:
    settings = Settings(
        _env_file=None, ALPACA_API_KEY_ID=KEY_ID, ALPACA_API_SECRET_KEY=SECRET
    )

    provider = default_registry().build("market", "alpaca", settings)

    assert isinstance(provider, AlpacaMarketProvider)
    assert provider.name == "alpaca"


@pytest.mark.parametrize(("key_id", "secret"), [("", SECRET), (KEY_ID, ""), ("", "")])
def test_registry_returns_none_when_a_key_is_missing(key_id: str, secret: str) -> None:
    settings = Settings(
        _env_file=None, ALPACA_API_KEY_ID=key_id, ALPACA_API_SECRET_KEY=secret
    )

    assert default_registry().build("market", "alpaca", settings) is None


def test_market_is_not_configured_when_alpaca_selected_without_key() -> None:
    settings = Settings(
        _env_file=None,
        MARKET_PROVIDER="alpaca",
        ALPACA_API_KEY_ID="",
        ALPACA_API_SECRET_KEY=SECRET,
    )

    providers = build_providers(settings)

    assert providers.market is None
    assert "market" in providers.not_configured


@respx.mock
def test_one_deadline_covers_every_request_of_the_call() -> None:
    clock = {"now": 1000.0}
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["adjustment"])
        clock["now"] += 7.0  # the raw request alone outlasts the 6 s budget
        return httpx.Response(
            200, json={"bars": _select(request), "next_page_token": None}
        )

    route(handler)
    provider = AlpacaMarketProvider(
        KEY_ID,
        SECRET,
        timeout_seconds=6.0,
        now=lambda: NOW_AFTER_CLOSE,
        sleep=lambda seconds: None,
    )
    provider._http._clock = lambda: clock["now"]  # noqa: SLF001

    with pytest.raises(VantageError) as exc:
        fetch(provider)

    assert requests == ["raw"]
    assert exc.value.code == "MARKET_DATA_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["unavailable"]
