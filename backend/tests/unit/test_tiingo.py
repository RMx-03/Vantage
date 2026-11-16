import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
import respx

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import ComponentQuality
from app.providers.registry import build_providers
from app.providers.tiingo import TIINGO_LIMITER, TiingoCrossCheckProvider

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

KEY = "tg-test-key-QWERTY1234567890"
URL = "https://api.tiingo.com/tiingo/daily/AAPL/prices"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "providers" / "tiingo"
START = date(2026, 11, 9)
END = date(2026, 11, 13)
RETRIEVED = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
PAYLOAD = json.loads((FIXTURES / "prices.json").read_text())

MESSAGES = {
    "auth": "Tiingo refused the configured API key.",
    "rate_limited": "Tiingo rate limit was reached.",
    "other": "Cross-check prices could not be retrieved.",
}


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    TIINGO_LIMITER._calls.clear()


def make_provider() -> TiingoCrossCheckProvider:
    return TiingoCrossCheckProvider(
        KEY, timeout_seconds=6.0, sleep=lambda seconds: None
    )


def fetch(provider: TiingoCrossCheckProvider, symbol: str = "aapl"):  # type: ignore[no-untyped-def]
    return provider.fetch_adjusted_closes(symbol, START, END, RETRIEVED)


def _chain_text(error: BaseException | None) -> str:
    parts = []
    while error is not None:
        parts.append(repr(error))
        parts.append(str(error))
        error = error.__cause__ or error.__context__
    return " ".join(parts)


@respx.mock
def test_happy_path_sends_the_header_and_no_token_in_the_query() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=PAYLOAD))

    snapshot = fetch(make_provider())

    request = route.calls[0].request
    assert request.headers["Authorization"] == f"Token {KEY}"
    assert "token" not in request.url.params
    assert KEY not in str(request.url)
    assert request.url.params["startDate"] == "2026-11-09"
    assert request.url.params["endDate"] == "2026-11-13"
    assert snapshot.provider == "tiingo"
    assert snapshot.symbol == "AAPL"
    assert snapshot.quality is ComponentQuality.FRESH
    assert snapshot.error_code is None
    assert snapshot.retrieved_at == RETRIEVED
    assert [c.session_date for c in snapshot.closes] == [
        date(2026, 11, 9),
        date(2026, 11, 10),
        date(2026, 11, 11),
        date(2026, 11, 12),
        date(2026, 11, 13),
    ]
    assert snapshot.closes[-1].adjusted_close == 271.8
    assert snapshot.closes[0].adjusted_close == 267.75


@respx.mock
def test_closes_are_sorted_and_non_positive_or_non_finite_are_dropped() -> None:
    body = [
        {"date": "2026-11-13T00:00:00.000Z", "adjClose": 272.0},
        {"date": "2026-11-12T00:00:00.000Z", "adjClose": 0},
        {"date": "2026-11-11T00:00:00.000Z", "adjClose": -1.5},
        {"date": "2026-11-10T00:00:00.000Z", "adjClose": None},
        {"date": "2026-11-09T00:00:00.000Z", "adjClose": "270"},
        {"date": "2026-11-08T00:00:00.000Z", "adjClose": True},
        {"date": "bad", "adjClose": 5.0},
        {"adjClose": 5.0},
        "junk",
        {"date": "2026-11-06T00:00:00.000Z", "adjClose": 269.5},
    ]
    respx.get(URL).mock(return_value=httpx.Response(200, json=body))

    snapshot = fetch(make_provider())

    assert [(c.session_date, c.adjusted_close) for c in snapshot.closes] == [
        (date(2026, 11, 6), 269.5),
        (date(2026, 11, 13), 272.0),
    ]


@respx.mock
def test_nothing_usable_after_filtering_is_missing() -> None:
    body = [{"date": "2026-11-13T00:00:00.000Z", "adjClose": 0}]
    respx.get(URL).mock(return_value=httpx.Response(200, json=body))

    snapshot = fetch(make_provider())

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "PRICE_CROSSCHECK_UNAVAILABLE"
    assert snapshot.closes == []


@respx.mock
def test_empty_list_is_missing() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=[]))

    snapshot = fetch(make_provider())

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "PRICE_CROSSCHECK_UNAVAILABLE"


@respx.mock
def test_dotted_symbol_is_requested_with_a_dash() -> None:
    route = respx.get("https://api.tiingo.com/tiingo/daily/BRK-B/prices").mock(
        return_value=httpx.Response(200, json=PAYLOAD)
    )

    snapshot = fetch(make_provider(), "brk.b")

    assert route.call_count == 1
    assert snapshot.symbol == "BRK.B"
    assert snapshot.quality is ComponentQuality.FRESH


@respx.mock
def test_404_is_missing_not_an_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(404, json={"detail": "x"}))

    snapshot = fetch(make_provider())

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "PRICE_CROSSCHECK_UNAVAILABLE"
    assert snapshot.closes == []


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_raises_with_its_message(status: int) -> None:
    respx.get(URL).mock(return_value=httpx.Response(status))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "PRICE_CROSSCHECK_FAILED"
    assert exc.value.safe_message == MESSAGES["auth"]


@respx.mock
def test_429_retries_once_then_raises_the_rate_limit_message() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(429))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "PRICE_CROSSCHECK_FAILED"
    assert exc.value.safe_message == MESSAGES["rate_limited"]
    assert route.call_count == 2


@respx.mock
def test_500_retries_once_then_raises_the_generic_message() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(500))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["other"]
    assert route.call_count == 2


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"detail": "x"}),
    ],
)
def test_malformed_body_raises(response: httpx.Response) -> None:
    respx.get(URL).mock(return_value=response)

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "PRICE_CROSSCHECK_FAILED"
    assert exc.value.safe_message == MESSAGES["other"]


@respx.mock
@pytest.mark.parametrize("status", [401, 429, 500])
def test_api_key_never_leaks(status: int, caplog: pytest.LogCaptureFixture) -> None:
    respx.get(URL).mock(return_value=httpx.Response(status, text=KEY))
    provider = make_provider()

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(VantageError) as exc:
            fetch(provider)

    assert exc.value.__cause__ is None
    for text in (_chain_text(exc.value), repr(provider), caplog.text):
        assert KEY not in text


@respx.mock
def test_connect_error_does_not_leak_into_the_chain() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError(f"boom {URL} {KEY}"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["other"]
    assert KEY not in _chain_text(exc.value)
    assert URL not in _chain_text(exc.value)


@respx.mock
def test_exhausted_limiter_refuses_without_a_request() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    for _ in range(40):
        TIINGO_LIMITER.acquire()

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "PRICE_CROSSCHECK_FAILED"
    assert exc.value.safe_message == MESSAGES["rate_limited"]
    assert route.call_count == 0


def test_repr_is_fixed() -> None:
    assert repr(make_provider()) == "TiingoCrossCheckProvider()"


def test_registry_builds_tiingo_only_with_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    keyed = build_providers(
        Settings(_env_file=None, PRICE_CROSSCHECK_PROVIDER="tiingo", TIINGO_API_KEY="k")
    )
    assert keyed.crosscheck is not None and keyed.crosscheck.name == "tiingo"
    assert "crosscheck" not in keyed.not_configured

    missing = build_providers(
        Settings(_env_file=None, PRICE_CROSSCHECK_PROVIDER="tiingo")
    )
    assert missing.crosscheck is None
    assert "crosscheck" in missing.not_configured

    default = build_providers(Settings(_env_file=None))
    assert default.crosscheck is None
