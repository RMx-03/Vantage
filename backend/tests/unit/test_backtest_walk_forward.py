from datetime import UTC, date, datetime

import numpy as np
import pytest

from app.backtest.engine import simulate
from app.backtest.inputs import HistoryInputs
from app.backtest.metrics import compute_metrics
from app.backtest.walk_forward import (
    TEST_SESSIONS,
    TRAIN_SESSIONS,
    build_windows,
    walk_forward,
)
from app.domain.experiments import ExperimentSpec


def _inputs(n: int = 1400, seed: int = 3) -> HistoryInputs:
    rng = np.random.default_rng(seed)
    closes = np.exp(np.cumsum(rng.normal(0.0003, 0.015, (n, 4)), axis=0)) * 50
    sessions = np.busday_offset("2018-01-02", np.arange(n), roll="forward")
    return HistoryInputs(
        symbols=("A", "B", "C"),
        benchmark="SPY",
        sessions=sessions.astype("datetime64[D]"),
        open_adj=closes * 1.001,
        close_adj=closes,
        dollar_volume=closes * 1e8,
        provider="fixture",
        retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


def _spec(inputs: HistoryInputs) -> ExperimentSpec:
    return ExperimentSpec.model_validate(
        {
            "question": "q",
            "symbols": list(inputs.symbols),
            "start": inputs.session_dates[0].isoformat(),
            "end": inputs.session_dates[-1].isoformat(),
            "strategy": {"template": "sma_crossover", "fast": 10, "slow": 50},
            "candidates": [
                {"template": "sma_crossover", "fast": 10, "slow": 50},
                {"template": "sma_crossover", "fast": 20, "slow": 100},
                {"template": "sma_crossover", "fast": 50, "slow": 200},
            ],
        }
    )


def test_windows_roll_without_overlapping_test_dates() -> None:
    windows = build_windows(n_sessions=1400, start=10)
    assert (
        len(windows)
        == (1400 - 10 - TRAIN_SESSIONS - TEST_SESSIONS) // TEST_SESSIONS + 1
    )
    for w in windows:
        assert w.train_end == w.test_start
        assert w.train_end - w.train_start == TRAIN_SESSIONS
        assert w.test_end - w.test_start == TEST_SESSIONS
    for a, b in zip(windows, windows[1:], strict=False):
        assert a.test_end == b.test_start
    assert windows[0].train_start == 10
    assert windows[-1].test_end <= 1400


def test_fewer_than_three_windows_is_insufficient() -> None:
    inputs = _inputs(n=1000)
    result = walk_forward(_spec(inputs), inputs, first_decision=0)
    assert result.status == "insufficient_data"
    assert result.oos_metrics is None
    assert result.trial_count == 3


def test_selection_uses_training_sharpe_and_records_every_trial() -> None:
    inputs = _inputs()
    spec = _spec(inputs)
    result = walk_forward(spec, inputs, first_decision=0)
    assert result.status == "complete"
    assert len(result.windows) >= 3
    assert [t.status for t in result.trials] == ["succeeded"] * 3
    from app.backtest.templates import targets

    ledgers = [
        simulate(targets(c, inputs, 0), inputs, spec.cost_bps) for c in spec.candidates
    ]
    dates = inputs.session_dates
    windows = build_windows(len(dates), 0)
    for w, recorded in zip(windows, result.windows, strict=True):
        sharpes = [
            compute_metrics(lg, dates, start=w.train_start, end=w.train_end).sharpe
            for lg in ledgers
        ]
        best = max(
            range(3), key=lambda i: sharpes[i] if sharpes[i] is not None else -1e9
        )
        assert recorded.selected == best
        assert recorded.train_sharpe == pytest.approx(sharpes[best])


def test_changing_a_test_window_never_changes_its_selection() -> None:
    inputs = _inputs()
    spec = _spec(inputs)
    base = walk_forward(spec, inputs, first_decision=0)
    windows = build_windows(len(inputs.sessions), 0)
    for k, w in enumerate(windows):
        bumped = inputs.close_adj.copy()
        bumped[w.test_start :] *= np.linspace(0.3, 3.0, len(bumped) - w.test_start)[
            :, None
        ]
        mutated = HistoryInputs(
            symbols=inputs.symbols,
            benchmark=inputs.benchmark,
            sessions=inputs.sessions,
            open_adj=bumped,
            close_adj=bumped,
            dollar_volume=inputs.dollar_volume,
            provider="fixture",
            retrieved_at=inputs.retrieved_at,
        )
        again = walk_forward(spec, mutated, first_decision=0)
        assert [x.selected for x in again.windows[: k + 1]] == [
            x.selected for x in base.windows[: k + 1]
        ]


def test_continuous_out_of_sample_curve_carries_holdings_and_pays_switch_costs() -> (
    None
):
    inputs = _inputs()
    spec = _spec(inputs)
    result = walk_forward(spec, inputs, first_decision=0)
    assert result.oos_series is not None and result.oos_metrics is not None
    windows = build_windows(len(inputs.sessions), 0)
    assert result.oos_series.dates[0] == inputs.session_dates[windows[0].test_start - 1]
    assert result.oos_series.dates[-1] == inputs.session_dates[windows[-1].test_end - 1]
    assert result.oos_series.nav[0] == pytest.approx(100_000)
    gross_minus_net = np.array(result.oos_series.gross_nav) - np.array(
        result.oos_series.nav
    )
    assert np.all(np.diff(gross_minus_net) >= -1e-9)  # costs only accumulate


def test_ties_break_on_lower_turnover_then_spec_hash() -> None:
    inputs = _inputs()
    spec = ExperimentSpec.model_validate(
        {
            "question": "q",
            "symbols": ["A", "B", "C"],
            "start": inputs.session_dates[0].isoformat(),
            "end": inputs.session_dates[-1].isoformat(),
            "strategy": {"template": "buy_and_hold"},
            "candidates": [{"template": "buy_and_hold"}, {"template": "buy_and_hold"}],
        }
    )
    result = walk_forward(spec, inputs, first_decision=0)
    assert {w.selected for w in result.windows} == {0}


def test_window_dates_are_reported() -> None:
    inputs = _inputs()
    result = walk_forward(_spec(inputs), inputs, first_decision=0)
    first = result.windows[0]
    assert isinstance(first.train_start, date)
    assert first.train_start < first.train_end <= first.test_start < first.test_end
