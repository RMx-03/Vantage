from datetime import UTC, date, datetime

import numpy as np

from app.backtest import run_experiment
from app.domain.experiments import ExperimentSpec
from app.providers.alpaca import AlpacaMarketProvider
from app.providers.fixture_provider import FixtureProvider
from app.providers.registry import history_provider
from app.services.sessions import XNYS

RETRIEVED = datetime(2025, 1, 2, tzinfo=UTC)


def _fetch(symbols: tuple[str, ...] = ("AAPL", "MSFT")) -> object:
    return FixtureProvider().fetch_daily_history(
        symbols, "SPY", date(2022, 1, 3), date(2023, 12, 29), RETRIEVED
    )


def test_fixture_history_is_deterministic_keyless_and_on_xnys_sessions() -> None:
    a, b = _fetch(), _fetch()
    np.testing.assert_array_equal(a.close_adj, b.close_adj)  # type: ignore[attr-defined]
    expected = [s.date() for s in XNYS.sessions_in_range("2022-01-03", "2023-12-29")]
    assert a.session_dates == expected  # type: ignore[attr-defined]
    assert a.names == ("AAPL", "MSFT", "SPY")  # type: ignore[attr-defined]
    assert (a.close_adj > 0).all() and (a.open_adj > 0).all()  # type: ignore[attr-defined]
    assert not np.isnan(a.dollar_volume).any()  # type: ignore[attr-defined]


def test_each_symbol_gets_its_own_series_independent_of_the_list() -> None:
    both = _fetch(("AAPL", "MSFT"))
    alone = _fetch(("MSFT",))
    assert not np.array_equal(both.close_adj[:, 0], both.close_adj[:, 1])  # type: ignore[attr-defined]
    np.testing.assert_array_equal(both.close_adj[:, 1], alone.close_adj[:, 0])  # type: ignore[attr-defined]


def test_fixture_history_runs_end_to_end() -> None:
    inputs = _fetch()
    spec = ExperimentSpec.model_validate(
        {
            "question": "q",
            "symbols": ["AAPL", "MSFT"],
            "start": "2022-03-01",
            "end": "2023-12-29",
            "strategy": {"template": "buy_and_hold"},
        }
    )
    result = run_experiment(spec, inputs)  # type: ignore[arg-type]
    assert result.metrics is not None


def test_history_provider_is_the_market_provider_when_it_supports_history() -> None:
    fixture = FixtureProvider()
    assert history_provider(fixture) is fixture
    alpaca = AlpacaMarketProvider("K", "S", timeout_seconds=1)
    assert history_provider(alpaca) is alpaca
    assert history_provider(None) is None
    assert history_provider(object()) is None


def test_the_default_registry_stays_cached_and_history_lookup_does_not() -> None:
    from app.providers.registry import default_registry, history_provider

    assert default_registry() is default_registry()
    assert not hasattr(history_provider, "cache_clear")
