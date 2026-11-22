import math
from datetime import UTC, date, datetime

import numpy as np
import pytest

from app.backtest.engine import Ledger, Trade
from app.backtest.inputs import HistoryInputs
from app.backtest.metrics import compute_metrics, liquidity_findings

DATES = [date(2024, 1, d) for d in (2, 3, 4, 5, 8)]


def _ledger(
    nav: list[float],
    cash: list[float] | None = None,
    traded: list[float] | None = None,
    costs: list[float] | None = None,
    trades: list[Trade] | None = None,
) -> Ledger:
    n = len(nav)
    zeros = [0.0] * n
    return Ledger(
        nav=np.array(nav),
        gross_nav=np.array(nav),
        cash=np.array(cash or zeros),
        holdings=np.zeros((n, 2)),
        traded=np.array(traded or zeros),
        costs=np.array(costs or zeros),
        trades=trades or [],
        deferred_fills=np.zeros(2, dtype=int),
    )


def test_returns_drawdown_and_ratios_by_hand() -> None:
    nav = [100.0, 110.0, 99.0, 99.0, 121.0]
    m = compute_metrics(_ledger(nav), DATES)
    r = np.array([0.1, -0.1, 0.0, 121 / 99 - 1])
    assert m.total_return == pytest.approx(0.21)
    assert m.cagr == pytest.approx(1.21 ** (252 / 4) - 1)
    assert m.volatility == pytest.approx(r.std(ddof=1) * math.sqrt(252))
    assert m.sharpe == pytest.approx(r.mean() / r.std(ddof=1) * math.sqrt(252))
    assert m.max_drawdown == pytest.approx(99 / 110 - 1)
    assert (m.max_drawdown_start, m.max_drawdown_end) == (
        date(2024, 1, 3),
        date(2024, 1, 4),
    )
    assert m.sessions == 4


def test_zero_variance_sharpe_is_null_with_a_reason() -> None:
    m = compute_metrics(_ledger([100.0] * 5), DATES)
    assert m.sharpe is None
    assert m.sharpe_note == "zero variance"
    assert m.max_drawdown == 0
    assert m.max_drawdown_start is None


def test_turnover_costs_and_exposure() -> None:
    nav = [100.0, 100.0, 100.0, 100.0, 100.0]
    cash = [100.0, 0.0, 0.0, 50.0, 50.0]
    traded = [0.0, 100.0, 0.0, 50.0, 0.0]
    costs = [0.0, 0.1, 0.0, 0.05, 0.0]
    m = compute_metrics(_ledger(nav, cash, traded, costs), DATES)
    assert m.turnover == pytest.approx(150 / 100)
    assert m.costs == pytest.approx(0.15 / 100)
    assert m.exposure == pytest.approx((0 + 1 + 1 + 0.5 + 0.5) / 5)


def test_evaluation_can_start_later() -> None:
    m = compute_metrics(_ledger([100.0, 50.0, 100.0, 110.0, 121.0]), DATES, start=2)
    assert m.total_return == pytest.approx(0.21)
    assert m.sessions == 2
    assert m.max_drawdown == 0


def test_large_fill_relative_to_dollar_volume_is_a_finding() -> None:
    dv = np.array([[1e6, 1e9], [1e6, 1e9], [1e6, 1e9], [1e6, 1e9], [1e6, 1e9]])
    inputs = HistoryInputs(
        symbols=("THIN",),
        benchmark="SPY",
        sessions=np.array(DATES, dtype="datetime64[D]"),
        open_adj=np.ones((5, 2)),
        close_adj=np.ones((5, 2)),
        dollar_volume=dv,
        provider="fixture",
        retrieved_at=datetime(2024, 2, 1, tzinfo=UTC),
    )
    trades = [
        Trade(
            session=1, name=0, shares=60_000, price=1.0, notional=60_000.0
        ),  # 6% of 1e6
        Trade(session=3, name=0, shares=-40_000, price=1.0, notional=-40_000.0),  # 4%
        Trade(session=3, name=1, shares=60_000, price=1.0, notional=60_000.0),
    ]
    findings = liquidity_findings(_ledger([1.0] * 5, trades=trades), inputs)
    assert [(f.code, f.symbol, f.count) for f in findings] == [
        ("LIQUIDITY_LIMIT_EXCEEDED", "THIN", 1)
    ]
