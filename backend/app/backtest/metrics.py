"""Simulation metrics and liquidity findings (backtest-metrics-v1)."""

import math
from datetime import date

import numpy as np

from app.backtest.engine import Ledger
from app.backtest.inputs import HistoryInputs
from app.domain.experiments import Finding, SimulationMetrics

METRICS_VERSION = "backtest-metrics-v1"
TRADING_DAYS = 252
LIQUIDITY_SHARE = 0.05
LIQUIDITY_WINDOW = 20


def compute_metrics(
    ledger: Ledger, sessions: list[date], start: int = 0
) -> SimulationMetrics:
    nav = ledger.nav[start:]
    returns = nav[1:] / nav[:-1] - 1
    n = len(returns)
    growth = float(nav[-1] / nav[0])

    volatility = sharpe = None
    note: str | None = "too few sessions"
    if n >= 2:
        std = float(returns.std(ddof=1))
        volatility = std * math.sqrt(TRADING_DAYS)
        if std > 1e-15:
            sharpe, note = float(returns.mean()) / std * math.sqrt(TRADING_DAYS), None
        else:
            note = "zero variance"

    drawdown = nav / np.maximum.accumulate(nav) - 1
    trough = int(np.argmin(drawdown))
    dd_start = dd_end = None
    if drawdown[trough] < 0:
        dd_start = sessions[start + int(np.argmax(nav[: trough + 1]))]
        dd_end = sessions[start + trough]

    return SimulationMetrics(
        sessions=n,
        total_return=growth - 1,
        cagr=growth ** (TRADING_DAYS / n) - 1 if n else None,
        volatility=volatility,
        sharpe=sharpe,
        sharpe_note=note,
        max_drawdown=float(drawdown[trough]),
        max_drawdown_start=dd_start,
        max_drawdown_end=dd_end,
        turnover=float(ledger.traded[start + 1 :].sum() / nav.mean()),
        costs=float(ledger.costs[start + 1 :].sum() / nav[0]),
        exposure=float(np.mean(1 - ledger.cash[start:] / nav)),
    )


def liquidity_findings(ledger: Ledger, inputs: HistoryInputs) -> list[Finding]:
    """Flag fills above 5% of the name's prior 20-session average dollar volume."""
    counts: dict[int, int] = {}
    for trade in ledger.trades:
        window = inputs.dollar_volume[
            max(0, trade.session - LIQUIDITY_WINDOW) : trade.session, trade.name
        ]
        window = window[~np.isnan(window)]
        if window.size and abs(trade.notional) > LIQUIDITY_SHARE * float(window.mean()):
            counts[trade.name] = counts.get(trade.name, 0) + 1
    return [
        Finding(
            code="LIQUIDITY_LIMIT_EXCEEDED",
            message=(
                f"{count} simulated fill(s) exceeded 5% of the prior 20-session average "
                "dollar volume; fills were not reduced."
            ),
            symbol=inputs.names[name],
            count=count,
        )
        for name, count in sorted(counts.items())
    ]
