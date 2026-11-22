"""Golden cases for the daily accounting engine.

Every expected number is written as the arithmetic a person would do by hand,
so a reader can check it without trusting the engine. Convention under test:
weights decided at close t fill at open t+1; costs are cost_bps of traded
notional, paid from the same NAV the weights apply to:
    x_i = w_i * (V_open - c * sum_j |x_j - h_j|)
"""

from datetime import UTC, datetime

import numpy as np
import pytest

from app.backtest.engine import simulate
from app.backtest.inputs import HistoryInputs

NAN = np.nan
CAP = 100_000.0
TOL = 1e-8


def _inputs(opens: list[list[float]], closes: list[list[float]]) -> HistoryInputs:
    o, c = np.array(opens, dtype=float), np.array(closes, dtype=float)
    n_sessions, n_names = o.shape
    sessions = np.datetime64("2024-01-02") + np.arange(n_sessions)
    return HistoryInputs(
        symbols=tuple(f"S{i}" for i in range(n_names - 1)),
        benchmark="SPY",
        sessions=sessions.astype("datetime64[D]"),
        open_adj=o,
        close_adj=c,
        dollar_volume=np.where(np.isnan(c), NAN, c * 1e7),
        provider="fixture",
        retrieved_at=datetime(2024, 2, 1, tzinfo=UTC),
    )


def _targets(rows: list[list[float] | None], n_names: int) -> np.ndarray:
    return np.array([[NAN] * n_names if r is None else r for r in rows], dtype=float)


def test_cash_only_keeps_capital() -> None:
    inputs = _inputs([[10, 50]] * 3, [[10, 50]] * 3)
    ledger = simulate(_targets([[0, 0]] * 3, 2), inputs, cost_bps=10)
    np.testing.assert_allclose(ledger.nav, [CAP, CAP, CAP], atol=TOL)
    assert ledger.costs.sum() == 0
    assert ledger.trades == []


def test_one_name_buy_and_hold_without_costs() -> None:
    inputs = _inputs([[10, 1], [11, 1], [12, 1]], [[10.5, 1], [11.5, 1], [12.5, 1]])
    ledger = simulate(_targets([[1, 0], None, None], 2), inputs, cost_bps=0)
    shares = CAP / 11
    np.testing.assert_allclose(
        ledger.nav, [CAP, shares * 11.5, shares * 12.5], atol=TOL
    )
    np.testing.assert_allclose(ledger.holdings[2], [shares, 0], atol=TOL)
    np.testing.assert_allclose(ledger.cash, [CAP, 0, 0], atol=TOL)


def test_buying_from_cash_pays_costs_out_of_the_same_capital() -> None:
    inputs = _inputs([[10, 1], [11, 1], [12, 1]], [[10.5, 1], [11.5, 1], [12.5, 1]])
    ledger = simulate(_targets([[1, 0], None, None], 2), inputs, cost_bps=10)
    c = 0.001
    bought = CAP / (1 + c)
    cost = c * bought
    shares = bought / 11
    np.testing.assert_allclose(ledger.costs, [0, cost, 0], atol=TOL)
    np.testing.assert_allclose(ledger.cash, [CAP, 0, 0], atol=TOL)
    np.testing.assert_allclose(ledger.nav[1:], [shares * 11.5, shares * 12.5], atol=TOL)
    np.testing.assert_allclose(ledger.gross_nav[1:], ledger.nav[1:] + cost, atol=TOL)


@pytest.mark.parametrize("cost_bps", [0, 10, 20])
def test_rotation_sells_one_name_and_buys_another(cost_bps: float) -> None:
    opens = [[10, 20, 1], [10, 20, 1], [12, 25, 1], [12, 25, 1]]
    closes = [[10, 20, 1], [11, 22, 1], [12, 25, 1], [13, 24, 1]]
    targets = _targets([[1, 0, 0], [0, 1, 0], None, None], 3)
    ledger = simulate(targets, _inputs(opens, closes), cost_bps=cost_bps)
    c = cost_bps / 10_000
    shares_a = CAP / (1 + c) / 10
    value_a = shares_a * 12  # sold at open 2
    bought_b = (value_a - c * value_a) / (1 + c)
    shares_b = bought_b / 25
    expected = [CAP, shares_a * 11, shares_b * 25, shares_b * 24]
    np.testing.assert_allclose(ledger.nav, expected, atol=TOL)
    np.testing.assert_allclose(ledger.holdings[3], [0, shares_b, 0], atol=TOL)
    np.testing.assert_allclose(ledger.traded[2], value_a + bought_b, atol=TOL)


def test_two_names_equal_weight() -> None:
    opens = [[10, 20, 1], [10, 20, 1], [10, 20, 1]]
    closes = [[10, 20, 1], [12, 18, 1], [11, 22, 1]]
    ledger = simulate(
        _targets([[0.5, 0.5, 0], None, None], 3), _inputs(opens, closes), 0
    )
    a, b = 50_000 / 10, 50_000 / 20
    np.testing.assert_allclose(
        ledger.nav, [CAP, a * 12 + b * 18, a * 11 + b * 22], atol=TOL
    )


def test_weights_below_one_leave_cash() -> None:
    opens = [[10, 1], [10, 1], [10, 1]]
    closes = [[10, 1], [10, 1], [12, 1]]
    ledger = simulate(_targets([[0.5, 0], None, None], 2), _inputs(opens, closes), 10)
    c = 0.001
    bought = 0.5 * CAP / (1 + 0.5 * c)
    cash = CAP - bought - c * bought
    np.testing.assert_allclose(ledger.cash[2], cash, atol=TOL)
    np.testing.assert_allclose(ledger.nav[2], cash + bought / 10 * 12, atol=TOL)
    assert ledger.cash.min() >= 0


def test_missing_open_makes_the_whole_decision_wait() -> None:
    opens = [[10, 20, 1], [10, NAN, 1], [10, 25, 1]]
    closes = [[10, 20, 1], [10, 21, 1], [10, 26, 1]]
    targets = _targets([[0.5, 0.5, 0], None, None], 3)
    ledger = simulate(targets, _inputs(opens, closes), 0)
    # Session 1: S1 has no open, so nothing fills and capital stays in cash.
    np.testing.assert_allclose(ledger.holdings[1], [0, 0, 0], atol=TOL)
    np.testing.assert_allclose(ledger.cash[1], CAP, atol=TOL)
    # Session 2: both halves fill together.
    np.testing.assert_allclose(ledger.holdings[2], [5_000, 50_000 / 25, 0], atol=TOL)
    np.testing.assert_allclose(ledger.nav[2], 5_000 * 10 + 2_000 * 26, atol=TOL)
    assert ledger.deferred_fills[1] == 1


def test_a_sale_waiting_for_an_open_never_borrows() -> None:
    # Hold S0 fully, then rotate into S1 on a session where S0 has no open.
    opens = [[10, 20, 1], [10, 20, 1], [NAN, 20, 1], [10, 20, 1]]
    closes = [[10, 20, 1], [10, 20, 1], [10, 20, 1], [10, 20, 1]]
    targets = _targets([[1, 0, 0], [0, 1, 0], None, None], 3)
    ledger = simulate(targets, _inputs(opens, closes), 0)
    np.testing.assert_allclose(ledger.holdings[2], [CAP / 10, 0, 0], atol=TOL)
    np.testing.assert_allclose(ledger.holdings[3], [0, CAP / 20, 0], atol=TOL)
    assert ledger.cash.min() >= -TOL
    assert ledger.deferred_fills[0] == 1


def test_random_gaps_never_borrow_or_go_short() -> None:
    rng = np.random.default_rng(7)
    n_sessions, n_names = 120, 5
    prices = 50 * np.exp(np.cumsum(rng.normal(0, 0.02, (n_sessions, n_names)), axis=0))
    opens = prices * np.exp(rng.normal(0, 0.005, prices.shape))
    opens[rng.random(prices.shape) < 0.08] = NAN
    rows: list[list[float] | None] = []
    for _ in range(n_sessions):
        if rng.random() < 0.3:
            w = rng.random(n_names) * (rng.random(n_names) < 0.6)
            rows.append(list(w / max(w.sum(), 1.0)))
        else:
            rows.append(None)
    ledger = simulate(
        _targets(rows, n_names), _inputs(opens.tolist(), prices.tolist()), 25
    )
    assert ledger.cash.min() >= -1e-6
    assert ledger.holdings.min() >= -1e-9


def test_trades_can_be_skipped_without_changing_any_value() -> None:
    opens = [[10, 20, 1], [10, 20, 1], [12, 18, 1], [11, 19, 1]]
    closes = [[10, 20, 1], [11, 19, 1], [12, 18, 1], [11, 20, 1]]
    targets = _targets([[1, 0, 0], [0, 1, 0], [0.5, 0.5, 0], None], 3)
    full = simulate(targets, _inputs(opens, closes), 10)
    lean = simulate(targets, _inputs(opens, closes), 10, record_trades=False)
    assert full.trades and lean.trades == []
    for field in ("nav", "gross_nav", "cash", "traded", "costs"):
        np.testing.assert_array_equal(getattr(lean, field), getattr(full, field))


def test_missing_close_values_at_the_last_close() -> None:
    opens = [[10, 1], [10, 1], [10, 1], [10, 1]]
    closes = [[10, 1], [11, 1], [NAN, 1], [13, 1]]
    ledger = simulate(
        _targets([[1, 0], None, None, None], 2), _inputs(opens, closes), 0
    )
    shares = CAP / 10
    np.testing.assert_allclose(
        ledger.nav, [CAP, shares * 11, shares * 11, shares * 13], atol=TOL
    )


def test_name_without_any_price_yet_cannot_be_bought() -> None:
    opens = [[NAN, 10, 1], [NAN, 10, 1], [20, 10, 1]]
    closes = [[NAN, 10, 1], [NAN, 10, 1], [20, 10, 1]]
    targets = _targets([[0.5, 0.5, 0], None, None], 3)
    ledger = simulate(targets, _inputs(opens, closes), 0)
    # The decision waits until every name it holds has an open.
    np.testing.assert_allclose(ledger.holdings[1], [0, 0, 0], atol=TOL)
    np.testing.assert_allclose(ledger.holdings[2], [50_000 / 20, 5_000, 0], atol=TOL)


def test_invalid_targets_are_rejected() -> None:
    inputs = _inputs([[10, 1]] * 2, [[10, 1]] * 2)
    with pytest.raises(ValueError):
        simulate(_targets([[0.7, 0.7], None], 2), inputs, 0)
    with pytest.raises(ValueError):
        simulate(_targets([[-0.1, 0], None], 2), inputs, 0)
    with pytest.raises(ValueError):
        simulate(np.array([[0.5, NAN], [0, 0]]), inputs, 0)
    with pytest.raises(ValueError):
        simulate(_targets([[1, 0]], 2), inputs, 0)
