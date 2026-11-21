from datetime import UTC, date, datetime

import numpy as np
import pytest

from app.backtest.inputs import HistoryInputs, inputs_hash, pack_inputs, unpack_inputs


def _inputs() -> HistoryInputs:
    sessions = np.array(
        ["2024-01-02", "2024-01-03", "2024-01-04"], dtype="datetime64[D]"
    )
    close = np.array([[10.0, 100.0], [11.0, np.nan], [12.0, 102.0]])
    return HistoryInputs(
        symbols=("AAPL",),
        benchmark="SPY",
        sessions=sessions,
        open_adj=close - 0.5,
        close_adj=close,
        dollar_volume=close * 1e6,
        provider="fixture",
        retrieved_at=datetime(2024, 1, 5, tzinfo=UTC),
    )


def test_columns_are_symbols_then_benchmark() -> None:
    inputs = _inputs()
    assert inputs.names == ("AAPL", "SPY")
    assert inputs.benchmark_index == 1
    assert inputs.session_dates[0] == date(2024, 1, 2)


def test_pack_round_trips_exactly_including_missing_values() -> None:
    original = _inputs()
    restored = unpack_inputs(pack_inputs(original))
    assert restored.names == original.names
    assert restored.provider == "fixture"
    assert restored.retrieved_at == original.retrieved_at
    np.testing.assert_array_equal(restored.sessions, original.sessions)
    np.testing.assert_array_equal(restored.close_adj, original.close_adj)
    np.testing.assert_array_equal(restored.open_adj, original.open_adj)
    np.testing.assert_array_equal(restored.dollar_volume, original.dollar_volume)
    assert np.isnan(restored.close_adj[1, 1])


def test_hash_is_stable_and_changes_with_any_value() -> None:
    a, b = _inputs(), _inputs()
    assert inputs_hash(a) == inputs_hash(b)
    assert inputs_hash(unpack_inputs(pack_inputs(a))) == inputs_hash(a)
    b.close_adj[2, 0] = 12.000001
    assert inputs_hash(a) != inputs_hash(b)


def test_shape_mismatch_is_rejected() -> None:
    good = _inputs()
    with pytest.raises(ValueError):
        HistoryInputs(
            symbols=good.symbols,
            benchmark=good.benchmark,
            sessions=good.sessions,
            open_adj=good.open_adj[:2],
            close_adj=good.close_adj,
            dollar_volume=good.dollar_volume,
            provider="fixture",
            retrieved_at=good.retrieved_at,
        )


def test_sessions_must_increase() -> None:
    good = _inputs()
    with pytest.raises(ValueError):
        HistoryInputs(
            symbols=good.symbols,
            benchmark=good.benchmark,
            sessions=good.sessions[::-1].copy(),
            open_adj=good.open_adj,
            close_adj=good.close_adj,
            dollar_volume=good.dollar_volume,
            provider="fixture",
            retrieved_at=good.retrieved_at,
        )
