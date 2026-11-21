"""Rolling walk-forward evaluation.

Training Sharpe picks a candidate (ties: lower turnover, then params hash);
the choice is frozen for the next test window. The continuous out-of-sample
curve is one simulation that switches templates at each window start, so it
carries cash and holdings across windows and pays the switching costs.
"""

import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np

from app.backtest.engine import Ledger, simulate
from app.backtest.inputs import HistoryInputs
from app.backtest.metrics import compute_metrics
from app.backtest.templates import targets
from app.domain.experiments import (
    CandidateTrial,
    ExperimentSpec,
    SimulationSeries,
    StrategyParams,
    WalkForwardResult,
    WalkForwardWindow,
)

TRAIN_SESSIONS = 756
TEST_SESSIONS = 126
STEP_SESSIONS = 126
MIN_WINDOWS = 3


@dataclass(frozen=True)
class Window:
    """Session indices; ends are exclusive."""

    train_start: int
    train_end: int
    test_start: int
    test_end: int


def build_windows(n_sessions: int, start: int) -> list[Window]:
    windows = []
    s = start
    while s + TRAIN_SESSIONS + TEST_SESSIONS <= n_sessions:
        train_end = s + TRAIN_SESSIONS
        windows.append(Window(s, train_end, train_end, train_end + TEST_SESSIONS))
        s += STEP_SESSIONS
    return windows


def params_hash(params: StrategyParams) -> str:
    canonical = json.dumps(params.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _state(rows: np.ndarray, index: int) -> np.ndarray:
    """The template's standing weights after the decision at ``index``."""
    decided = np.flatnonzero(~np.isnan(rows[: index + 1]).all(axis=1))
    return rows[decided[-1]] if decided.size else np.zeros(rows.shape[1])


def series_of(ledger: Ledger, dates: list, start: int, stop: int) -> SimulationSeries:
    return SimulationSeries(
        dates=dates[start:stop],
        nav=ledger.nav[start:stop].tolist(),
        gross_nav=ledger.gross_nav[start:stop].tolist(),
    )


def walk_forward(
    spec: ExperimentSpec, inputs: HistoryInputs, first_decision: int
) -> WalkForwardResult:
    dates = inputs.session_dates
    windows = build_windows(len(dates), first_decision)
    candidates = spec.candidates
    if len(windows) < MIN_WINDOWS:
        return WalkForwardResult(
            status="insufficient_data",
            windows=[],
            trials=[
                CandidateTrial(index=i, params=c, status="not_run")
                for i, c in enumerate(candidates)
            ],
            trial_count=len(candidates),
        )

    runs: list[tuple[np.ndarray, Ledger] | None] = []
    trials = []
    for i, params in enumerate(candidates):
        try:
            rows = targets(params, inputs, first_decision)
            runs.append((rows, simulate(rows, inputs, spec.cost_bps)))
            trials.append(CandidateTrial(index=i, params=params, status="succeeded"))
        except ValueError as exc:
            runs.append(None)
            trials.append(
                CandidateTrial(index=i, params=params, status="failed", error=str(exc))
            )

    selections: list[int | None] = []
    reported = []
    for w in windows:
        best: int | None = None
        best_key: tuple[float, float, str] | None = None
        best_sharpe: float | None = None
        for i, run in enumerate(runs):
            if run is None:
                continue
            m = compute_metrics(run[1], dates, start=w.train_start, end=w.train_end)
            key = (
                -m.sharpe if m.sharpe is not None else math.inf,
                m.turnover,
                params_hash(candidates[i]),
            )
            if best_key is None or key < best_key:
                best, best_key, best_sharpe = i, key, m.sharpe
        selections.append(best)
        reported.append(
            WalkForwardWindow(
                train_start=dates[w.train_start],
                train_end=dates[w.train_end - 1],
                test_start=dates[w.test_start],
                test_end=dates[w.test_end - 1],
                selected=best,
                train_sharpe=best_sharpe,
            )
        )

    if any(s is None for s in selections):
        return WalkForwardResult(
            status="insufficient_data",
            windows=reported,
            trials=trials,
            trial_count=len(candidates),
        )

    combined = np.full(inputs.close_adj.shape, np.nan)
    for w, sel in zip(windows, selections, strict=True):
        run = runs[sel]  # type: ignore[index]
        assert run is not None
        rows = run[0]
        combined[w.test_start : w.test_end] = rows[w.test_start : w.test_end]
        combined[w.test_start - 1] = _state(rows, w.test_start - 1)
    oos = simulate(combined, inputs, spec.cost_bps)
    start, stop = windows[0].test_start - 1, windows[-1].test_end
    return WalkForwardResult(
        status="complete",
        windows=reported,
        trials=trials,
        trial_count=len(candidates),
        oos_metrics=compute_metrics(oos, dates, start=start, end=stop),
        oos_series=series_of(oos, dates, start, stop),
    )
