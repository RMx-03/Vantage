from datetime import UTC, datetime

import numpy as np
import pytest

from app.backtest.inputs import HistoryInputs
from app.backtest.templates import (
    benchmark_targets,
    month_ends,
    targets,
    warmup_sessions,
)
from app.domain.experiments import (
    BuyAndHoldParams,
    MomentumTopKParams,
    SmaCrossoverParams,
)

NAN = np.nan


def _inputs(closes: np.ndarray, start: str = "2024-01-02") -> HistoryInputs:
    sessions = np.busday_offset(start, np.arange(closes.shape[0]), roll="forward")
    return HistoryInputs(
        symbols=tuple(f"S{i}" for i in range(closes.shape[1] - 1)),
        benchmark="SPY",
        sessions=sessions.astype("datetime64[D]"),
        open_adj=closes.copy(),
        close_adj=closes,
        dollar_volume=closes * 1e7,
        provider="fixture",
        retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


def _decided(t: np.ndarray) -> list[int]:
    return [int(i) for i in np.flatnonzero(~np.isnan(t).all(axis=1))]


def test_warmup_sessions() -> None:
    assert warmup_sessions(BuyAndHoldParams()) == 0
    assert warmup_sessions(SmaCrossoverParams(fast=10, slow=50)) == 50
    assert warmup_sessions(MomentumTopKParams(lookback=126, k=1)) == 127


def test_buy_and_hold_decides_once_equal_weight_without_benchmark() -> None:
    closes = np.ones((5, 3)) * 10
    t = targets(BuyAndHoldParams(), _inputs(closes), first_decision=1)
    assert _decided(t) == [1]
    np.testing.assert_allclose(t[1], [0.5, 0.5, 0])


def test_buy_and_hold_skips_a_name_not_yet_listed() -> None:
    closes = np.ones((5, 3)) * 10
    closes[:3, 1] = NAN
    t = targets(BuyAndHoldParams(), _inputs(closes), first_decision=1)
    np.testing.assert_allclose(t[1], [1, 0, 0])


def test_benchmark_targets_hold_only_the_benchmark() -> None:
    t = benchmark_targets(_inputs(np.ones((4, 3))), first_decision=2)
    assert _decided(t) == [2]
    np.testing.assert_allclose(t[2], [0, 0, 1])


def test_sma_crossover_enters_and_exits_on_changes_only() -> None:
    # fast=5 over slow=20: flat, then rising (cross up), then falling (cross down).
    prices = np.concatenate(
        [np.full(25, 10.0), np.linspace(10, 20, 15), np.linspace(20, 5, 20)]
    )
    closes = np.column_stack([prices, np.ones_like(prices)])
    t = targets(SmaCrossoverParams(fast=5, slow=20), _inputs(closes), first_decision=0)
    decided = _decided(t)
    entries = [i for i in decided if t[i, 0] == 1]
    exits = [i for i in decided if t[i, 0] == 0]
    assert decided[0] == 19  # first session with a full slow window: holds cash
    assert t[19, 0] == 0
    assert entries and exits and entries[0] < exits[-1]
    assert all(25 < i < 40 for i in entries)
    # Between decisions nothing is re-decided.
    assert len(decided) == 3


def test_sma_crossover_splits_weight_across_held_names() -> None:
    rising = np.linspace(10, 30, 60)
    closes = np.column_stack([rising, rising * 2, np.ones(60)])
    t = targets(SmaCrossoverParams(fast=5, slow=20), _inputs(closes), first_decision=0)
    np.testing.assert_allclose(t[_decided(t)[0]], [0.5, 0.5, 0])


def test_momentum_rebalances_at_month_end_with_one_over_k() -> None:
    n = 200
    days = np.arange(n, dtype=float)
    closes = np.column_stack([100 + days, 100 + 2 * days, 100 - 0.1 * days, np.ones(n)])
    inputs = _inputs(closes)
    t = targets(MomentumTopKParams(lookback=126, k=2), inputs, first_decision=0)
    dates = inputs.session_dates
    for i in _decided(t):
        assert dates[i].month != dates[i + 1].month  # decided at a month's last close
        assert i >= 126
        np.testing.assert_allclose(t[i], [0.5, 0.5, 0, 0])


def test_month_end_is_the_last_session_in_the_data() -> None:
    # 2024-03-29 was Good Friday (XNYS closed), so March's last session is 03-28.
    sessions = np.array(
        np.busday_offset("2024-03-25", np.arange(8), holidays=["2024-03-29"]),
        dtype="datetime64[D]",
    )
    mask = month_ends(sessions)
    ends = [str(d) for d in sessions[mask]]
    assert ends == ["2024-03-28"]  # the final session is never a decided month end


def test_late_listing_is_ineligible_until_its_own_warmup() -> None:
    closes = np.column_stack(
        [np.linspace(10, 30, 80), np.linspace(10, 40, 80), np.ones(80)]
    )
    closes[:30, 1] = NAN
    t = targets(SmaCrossoverParams(fast=5, slow=20), _inputs(closes), first_decision=0)
    for i in _decided(t):
        if i < 30 + 19:
            assert t[i, 1] == 0


@pytest.mark.parametrize(
    "params",
    [
        BuyAndHoldParams(),
        SmaCrossoverParams(fast=5, slow=20),
        MomentumTopKParams(lookback=126, k=2),
    ],
)
def test_no_look_ahead(params: object) -> None:
    rng = np.random.default_rng(7)
    closes = np.exp(np.cumsum(rng.normal(0, 0.02, (300, 4)), axis=0)) * 50
    base = targets(params, _inputs(closes), first_decision=0)  # type: ignore[arg-type]
    for cut in (130, 180, 250):
        mutated = closes.copy()
        mutated[cut + 1 :] *= rng.uniform(0.2, 5.0, mutated[cut + 1 :].shape)
        again = targets(params, _inputs(mutated), first_decision=0)  # type: ignore[arg-type]
        np.testing.assert_array_equal(base[: cut + 1], again[: cut + 1])
