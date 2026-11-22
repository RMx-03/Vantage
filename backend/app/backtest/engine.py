"""Daily long-only accounting (research simulation only, never an order).

``targets[t]`` holds the weights decided at close t; they fill at the open of
session t+1. A row of NaN means "no new decision". Prices are total-return
adjusted, so splits and dividends need no separate handling. Costs are
``cost_bps`` of traded notional, paid out of the same capital the weights
apply to:  x_i = w_i * (V_open - c * sum_j |x_j - h_j|).
If a name the decision holds or would hold has no open at the fill session, the
whole decision waits for the next session where they all do, so sales always
fund purchases and cash never goes negative. Holdings without a close are
valued at their last close.
"""

from dataclasses import dataclass

import numpy as np

from app.backtest.inputs import HistoryInputs

DEFAULT_CAPITAL = 100_000.0
_WEIGHT_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Trade:
    session: int
    name: int
    shares: float
    price: float
    notional: float  # signed: positive buys, negative sells


@dataclass(frozen=True)
class Ledger:
    nav: np.ndarray  # (sessions,) after costs
    gross_nav: np.ndarray  # nav plus cumulative costs
    cash: np.ndarray
    holdings: np.ndarray  # (sessions, names) shares at the close
    traded: np.ndarray  # (sessions,) absolute traded notional
    costs: np.ndarray  # (sessions,)
    trades: list[Trade]
    deferred_fills: np.ndarray  # (names,) sessions a fill waited for an open


def _check_targets(targets: np.ndarray, shape: tuple[int, int]) -> None:
    if targets.shape != shape:
        raise ValueError(f"targets must have shape {shape}")
    decided = ~np.isnan(targets).all(axis=1)
    rows = targets[decided]
    if np.isnan(rows).any():
        raise ValueError("a decision row must be fully specified or fully NaN")
    if (rows < 0).any() or (rows.sum(axis=1) > 1 + _WEIGHT_TOLERANCE).any():
        raise ValueError("weights must be non-negative and sum to at most 1")


def _solve_cost(w: np.ndarray, held: np.ndarray, value: float, c: float) -> float:
    cost = 0.0
    for _ in range(200):
        nxt = c * float(np.abs(w * (value - cost) - held).sum())
        if abs(nxt - cost) < 1e-13:
            return nxt
        cost = nxt
    return cost


def simulate(
    targets: np.ndarray,
    inputs: HistoryInputs,
    cost_bps: float,
    capital: float = DEFAULT_CAPITAL,
    record_trades: bool = True,
) -> Ledger:
    """Simulate the targets; ``record_trades=False`` keeps memory flat for runs
    whose fills nobody reads (walk-forward candidates, cost stress, benchmark)."""
    opens, closes = inputs.open_adj, inputs.close_adj
    n_sessions, n_names = closes.shape
    _check_targets(targets, (n_sessions, n_names))
    c = cost_bps / 10_000

    nav = np.zeros(n_sessions)
    cash_series = np.zeros(n_sessions)
    holdings = np.zeros((n_sessions, n_names))
    traded = np.zeros(n_sessions)
    costs = np.zeros(n_sessions)
    deferred_fills = np.zeros(n_names, dtype=int)
    trades: list[Trade] = []

    shares = np.zeros(n_names)
    cash = capital
    last_close = np.full(n_names, np.nan)
    pending: np.ndarray | None = None

    for t in range(n_sessions):
        if pending is not None:
            has_open = ~np.isnan(opens[t])
            involved = (pending > 0) | (shares != 0)
            waiting = involved & ~has_open
            if waiting.any():
                deferred_fills[waiting] += 1
            else:
                fill = involved
                values = shares * np.where(has_open, opens[t], 0.0)
                open_value = cash + float(values.sum())
                w, held = pending[fill], values[fill]
                cost = _solve_cost(w, held, open_value, c)
                target_values = w * (open_value - cost)
                delta = target_values - held
                prices = opens[t][fill]
                shares[fill] = target_values / prices
                cash -= float(delta.sum()) + cost
                costs[t], traded[t] = cost, float(np.abs(delta).sum())
                for idx, d, p in zip(np.flatnonzero(fill), delta, prices, strict=True):
                    if record_trades and abs(d) > 1e-9:
                        trades.append(
                            Trade(t, int(idx), float(d / p), float(p), float(d))
                        )
                pending = None

        last_close = np.where(np.isnan(closes[t]), last_close, closes[t])
        held_value = float(np.where(shares != 0, shares * last_close, 0.0).sum())
        nav[t] = cash + held_value
        cash_series[t] = cash
        holdings[t] = shares

        if not np.isnan(targets[t]).all():
            pending = targets[t].copy()

    return Ledger(
        nav=nav,
        gross_nav=nav + np.cumsum(costs),
        cash=cash_series,
        holdings=holdings,
        traded=traded,
        costs=costs,
        trades=trades,
        deferred_fills=deferred_fills,
    )
