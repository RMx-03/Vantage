from datetime import UTC, date, datetime

import numpy as np
import pytest

from app.backtest import ExperimentDataError, run_experiment
from app.backtest.inputs import HistoryInputs
from app.domain.experiments import SURVIVORSHIP_LABEL, ExperimentSpec
from app.domain.research import ResearchStatus

NAN = np.nan


def _inputs(closes: np.ndarray, start: str = "2019-01-02") -> HistoryInputs:
    sessions = np.busday_offset(start, np.arange(closes.shape[0]), roll="forward")
    return HistoryInputs(
        symbols=tuple(f"S{i}" for i in range(closes.shape[1] - 1)),
        benchmark="SPY",
        sessions=sessions.astype("datetime64[D]"),
        open_adj=closes.copy(),
        close_adj=closes,
        dollar_volume=np.where(np.isnan(closes), NAN, 1e10),
        provider="fixture",
        retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


def _walk(n: int, names: int = 3, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.exp(np.cumsum(rng.normal(0.0004, 0.012, (n, names)), axis=0)) * 40


def _spec(
    inputs: HistoryInputs, start_index: int = 0, **extra: object
) -> ExperimentSpec:
    raw: dict[str, object] = {
        "question": "Does the template behave as described after costs?",
        "symbols": list(inputs.symbols),
        "start": inputs.session_dates[start_index].isoformat(),
        "end": inputs.session_dates[-1].isoformat(),
        "strategy": {"template": "buy_and_hold"},
    }
    raw.update(extra)
    return ExperimentSpec.model_validate(raw)


def test_full_result_has_metrics_benchmark_stress_label_and_hash() -> None:
    inputs = _inputs(_walk(300))
    result = run_experiment(_spec(inputs, start_index=1), inputs)
    assert result.label == SURVIVORSHIP_LABEL
    assert result.research_status == ResearchStatus.INFORMATIONAL
    assert result.metrics is not None and result.benchmark_metrics is not None
    assert [s.multiplier for s in result.cost_stress] == [0.5, 1.0, 2.0]
    assert [s.cost_bps for s in result.cost_stress] == [5.0, 10.0, 20.0]
    stress = [s.metrics.total_return for s in result.cost_stress]
    assert stress[0] >= stress[1] >= stress[2]
    assert result.cost_stress[1].metrics == result.metrics
    assert result.walk_forward is None
    assert result.series is not None
    assert (
        result.series.dates[0] == inputs.session_dates[0]
    )  # decision close before start
    assert len(result.series.nav) == len(result.series.benchmark_nav)
    assert result.trades and result.trades[0].session == inputs.session_dates[1]
    assert len(result.result_hash) == 64


def test_same_inputs_give_the_same_hash() -> None:
    inputs = _inputs(_walk(300))
    spec = _spec(inputs, start_index=1)
    assert (
        run_experiment(spec, inputs).result_hash
        == run_experiment(spec, inputs).result_hash
    )


def test_too_few_sessions_is_insufficient_data_without_simulation() -> None:
    inputs = _inputs(_walk(15))
    result = run_experiment(_spec(inputs, start_index=1), inputs)
    assert result.research_status == ResearchStatus.INSUFFICIENT_DATA
    assert result.metrics is None and result.series is None


def test_symbol_without_bars_fails() -> None:
    closes = _walk(100)
    closes[:, 1] = NAN
    with pytest.raises(ExperimentDataError) as err:
        run_experiment(_spec(_inputs(closes), 1), _inputs(closes))
    assert (err.value.code, err.value.symbol) == ("SYMBOL_NOT_FOUND", "S1")


def test_history_that_ends_early_fails_instead_of_exiting_at_a_last_quote() -> None:
    closes = _walk(100)
    closes[90:, 0] = NAN
    with pytest.raises(ExperimentDataError) as err:
        run_experiment(_spec(_inputs(closes), 1), _inputs(closes))
    assert (err.value.code, err.value.symbol) == ("INSTRUMENT_DATA_ENDED", "S0")
    assert err.value.last_session == date(2019, 5, 7)


def test_benchmark_gaps_are_checked_too() -> None:
    closes = _walk(100)
    closes[95:, 2] = NAN
    with pytest.raises(ExperimentDataError) as err:
        run_experiment(_spec(_inputs(closes), 1), _inputs(closes))
    assert err.value.symbol == "SPY"


def test_too_many_missing_sessions_fails() -> None:
    closes = _walk(100)
    closes[10:20, 1] = NAN
    with pytest.raises(ExperimentDataError) as err:
        run_experiment(_spec(_inputs(closes), 1), _inputs(closes))
    assert err.value.code == "INSUFFICIENT_HISTORY"


def test_few_missing_sessions_and_late_listing_are_findings() -> None:
    closes = _walk(200)
    closes[50:53, 0] = NAN
    closes[:40, 1] = NAN
    result = run_experiment(_spec(_inputs(closes), 1), _inputs(closes))
    codes = {(f.code, f.symbol) for f in result.findings}
    assert ("MISSING_SESSIONS", "S0") in codes
    assert ("INSTRUMENT_STARTS_LATE", "S1") in codes
    assert result.research_status == ResearchStatus.REVIEW


def test_walk_forward_runs_when_candidates_are_given() -> None:
    inputs = _inputs(_walk(1300, seed=4))
    spec = _spec(
        inputs,
        start_index=60,
        strategy={"template": "sma_crossover", "fast": 10, "slow": 50},
        candidates=[
            {"template": "sma_crossover", "fast": 10, "slow": 50},
            {"template": "sma_crossover", "fast": 20, "slow": 60},
        ],
    )
    result = run_experiment(spec, inputs)
    assert result.walk_forward is not None
    assert result.walk_forward.status == "complete"


def test_short_walk_forward_is_a_finding() -> None:
    inputs = _inputs(_walk(400, seed=4))
    spec = _spec(
        inputs,
        start_index=1,
        candidates=[{"template": "buy_and_hold"}],
    )
    result = run_experiment(spec, inputs)
    assert result.walk_forward is not None
    assert result.walk_forward.status == "insufficient_data"
    assert "WALK_FORWARD_INSUFFICIENT_DATA" in {f.code for f in result.findings}


def test_stored_trades_are_capped_but_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.backtest as backtest

    inputs = _inputs(_walk(300, names=6))
    spec = _spec(
        inputs,
        start_index=1,
        strategy={"template": "sma_crossover", "fast": 5, "slow": 20},
    )
    full = run_experiment(spec, inputs)
    assert full.trade_count == len(full.trades) > 4

    monkeypatch.setattr(backtest, "MAX_STORED_TRADES", 4)
    capped = run_experiment(spec, inputs)
    assert capped.trades == full.trades[:4]
    assert capped.trade_count == full.trade_count
    assert capped.metrics == full.metrics
