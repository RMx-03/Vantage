from datetime import UTC, date, datetime
from typing import Any

import httpx
import numpy as np
import pytest
import respx

from app.backtest import ExperimentDataError, validate_inputs
from app.domain.errors import VantageError
from app.providers.alpaca import ALPACA_LIMITER, AlpacaMarketProvider

URL = "https://data.alpaca.markets/v2/stocks/bars"
SESSIONS = [date(2024, 3, d) for d in (25, 26, 27, 28)]  # 03-29 Good Friday
AFTER = datetime(2024, 4, 2, 12, 0, tzinfo=UTC)
RETRIEVED = datetime(2024, 4, 2, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    ALPACA_LIMITER._calls.clear()


def _bar(day: date, o: float, c: float, v: float = 1000) -> dict[str, Any]:
    return {"t": f"{day.isoformat()}T04:00:00Z", "o": o, "h": c, "l": o, "c": c, "v": v}


def _provider(now: datetime = AFTER) -> AlpacaMarketProvider:
    return AlpacaMarketProvider(
        "KEY", "SECRET", timeout_seconds=5, now=lambda: now, sleep=lambda _: None
    )


def _route(pages: dict[str, list[dict[str, Any]]]) -> respx.Route:
    """Serve 'all' as raw prices doubled (as if adjusted), split into two pages."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        assert params["feed"] == "sip" and params["timeframe"] == "1Day"
        factor = 0.5 if params["adjustment"] == "all" else 1.0
        bars = {
            sym: [{**b, "o": b["o"] * factor, "c": b["c"] * factor} for b in rows]
            for sym, rows in pages.items()
            if sym in params["symbols"].split(",")
        }
        if "page_token" not in params:
            first = {s: r[:2] for s, r in bars.items()}
            return httpx.Response(200, json={"bars": first, "next_page_token": "p2"})
        rest = {s: r[2:] for s, r in bars.items()}
        return httpx.Response(200, json={"bars": rest, "next_page_token": None})

    return respx.get(URL).mock(side_effect=handler)


@respx.mock
def test_history_joins_adjusted_prices_and_raw_dollar_volume_across_pages() -> None:
    data = {
        "AAPL": [_bar(d, 10 + i, 11 + i, 100) for i, d in enumerate(SESSIONS)],
        "SPY": [_bar(d, 400 + i, 401 + i, 5) for i, d in enumerate(SESSIONS)],
    }
    route = _route(data)
    inputs = _provider().fetch_daily_history(
        ("AAPL",), "SPY", SESSIONS[0], SESSIONS[-1], RETRIEVED
    )
    assert route.call_count == 4  # raw and adjusted, two pages each
    assert inputs.session_dates == SESSIONS
    assert inputs.names == ("AAPL", "SPY")
    assert inputs.provider == "alpaca"
    np.testing.assert_allclose(inputs.open_adj[:, 0], [5, 5.5, 6, 6.5])
    np.testing.assert_allclose(inputs.close_adj[:, 1], [200.5, 201, 201.5, 202])
    np.testing.assert_allclose(inputs.dollar_volume[:, 0], [1100, 1200, 1300, 1400])


@respx.mock
def test_missing_bars_are_nan_and_an_unknown_symbol_fails_validation() -> None:
    data = {
        "AAPL": [_bar(d, 10, 11) for d in SESSIONS if d != SESSIONS[1]],
        "SPY": [_bar(d, 400, 401) for d in SESSIONS],
    }
    _route(data)
    inputs = _provider().fetch_daily_history(
        ("ZZZZ", "AAPL"), "SPY", SESSIONS[0], SESSIONS[-1], RETRIEVED
    )
    assert np.isnan(inputs.close_adj[1, 1])
    assert np.isnan(inputs.close_adj[:, 0]).all()
    with pytest.raises(ExperimentDataError) as err:
        validate_inputs(inputs)
    assert (err.value.code, err.value.symbol) == ("SYMBOL_NOT_FOUND", "ZZZZ")


@respx.mock
def test_benchmark_already_in_symbols_is_fetched_once() -> None:
    data = {"SPY": [_bar(d, 400, 401) for d in SESSIONS]}
    route = _route(data)
    inputs = _provider().fetch_daily_history(
        ("SPY",), "SPY", SESSIONS[0], SESSIONS[-1], RETRIEVED
    )
    assert route.calls[0].request.url.params["symbols"] == "SPY"
    np.testing.assert_array_equal(inputs.close_adj[:, 0], inputs.close_adj[:, 1])


@respx.mock
def test_end_is_clamped_to_the_sip_delay() -> None:
    data = {
        "AAPL": [_bar(d, 10, 11) for d in SESSIONS],
        "SPY": [_bar(d, 1, 1) for d in SESSIONS],
    }
    route = _route(data)
    during_lag = datetime(2024, 3, 28, 20, 10, tzinfo=UTC)  # 16:10 New York
    inputs = _provider(now=during_lag).fetch_daily_history(
        ("AAPL",), "SPY", SESSIONS[0], SESSIONS[-1], RETRIEVED
    )
    assert inputs.session_dates == SESSIONS[:3]
    assert route.calls[0].request.url.params["end"] == "2024-03-28T19:54:00Z"


@respx.mock
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(429), "Market data provider rate limit was reached."),
        (
            httpx.Response(401),
            "Market data provider refused the configured credentials.",
        ),
        (
            httpx.Response(200, json={"bars": {"AAPL": [{"t": "not a date"}]}}),
            "Market data provider returned an unreadable response.",
        ),
        (
            httpx.Response(
                200, json={"bars": {"AAPL": [{**_bar(SESSIONS[0], 1, 1), "c": "x"}]}}
            ),
            "Market data provider returned an unreadable response.",
        ),
    ],
)
def test_provider_failures_are_typed(response: httpx.Response, message: str) -> None:
    respx.get(URL).mock(return_value=response)
    with pytest.raises(VantageError) as err:
        _provider().fetch_daily_history(
            ("AAPL",), "SPY", SESSIONS[0], SESSIONS[-1], RETRIEVED
        )
    assert err.value.code == "MARKET_DATA_PROVIDER_FAILED"
    assert err.value.safe_message == message
