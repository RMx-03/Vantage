import math
from datetime import UTC, date, datetime, timedelta

from pydantic import ValidationError
import pytest

from app.domain.research import DailyBar, MarketSnapshot
from app.services.metrics import calculate_metrics


def snapshot(closes: list[float]) -> MarketSnapshot:
    bars: list[DailyBar] = []
    for i, c in enumerate(closes):
        try:
            bar = DailyBar(
                symbol="AAPL",
                session_date=date(2026, 8, 14) + timedelta(days=i),
                open=c if c > 0 and math.isfinite(c) else 100.0,
                high=c if c > 0 and math.isfinite(c) else 100.0,
                low=c if c > 0 and math.isfinite(c) else 100.0,
                close=c if c > 0 and math.isfinite(c) else 100.0,
                adjusted_close=c,
                volume=1_000_000,
                currency="USD",
                provider="fixture",
                retrieved_at=datetime(2026, 9, 14, tzinfo=UTC),
                adjustment_state="split_adjusted",
            )
        except ValidationError:
            bar = DailyBar.model_construct(
                symbol="AAPL",
                session_date=date(2026, 8, 14) + timedelta(days=i),
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                adjusted_close=c,
                volume=1_000_000,
                currency="USD",
                provider="fixture",
                retrieved_at=datetime(2026, 9, 14, tzinfo=UTC),
                adjustment_state="split_adjusted",
            )
        bars.append(bar)

    session = bars[-1].session_date if bars else date(2026, 9, 14)
    return MarketSnapshot(
        symbol="AAPL",
        bars=bars,
        provider="fixture",
        retrieved_at=datetime(2026, 9, 14, tzinfo=UTC),
        as_of=datetime(2026, 9, 14, tzinfo=UTC),
        latest_completed_session=session,
        content_hash="a" * 64,
    )


def test_returns_drawdown_and_liquidity_are_golden() -> None:
    values = {m.key: m.value for m in calculate_metrics(snapshot([100.0] * 20 + [110.0]))}
    assert values["return_1_session"] == pytest.approx(0.10)
    assert values["return_5_sessions"] == pytest.approx(0.10)
    assert values["return_20_sessions"] == pytest.approx(0.10)
    assert values["max_drawdown_20"] == pytest.approx(0.0)
    assert values["average_dollar_volume_20"] == pytest.approx(100_500_000.0)
    assert values["price_observation_count"] == 21


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_close_never_serializes_as_zero(bad: float) -> None:
    with pytest.raises(ValueError, match="INVALID_PRICE_SERIES"):
        calculate_metrics(snapshot([100.0] * 20 + [bad]))


def test_duplicate_session_date_rejected() -> None:
    bars = [
        DailyBar(
            symbol="AAPL",
            session_date=date(2026, 9, 11),
            open=100.0,
            high=105.0,
            low=99.0,
            close=102.0,
            adjusted_close=102.0,
            volume=1_000_000,
            currency="USD",
            provider="fixture",
            retrieved_at=datetime(2026, 9, 14, tzinfo=UTC),
            adjustment_state="split_adjusted",
        ),
        DailyBar(
            symbol="AAPL",
            session_date=date(2026, 9, 11),
            open=102.0,
            high=104.0,
            low=101.0,
            close=103.0,
            adjusted_close=103.0,
            volume=1_000_000,
            currency="USD",
            provider="fixture",
            retrieved_at=datetime(2026, 9, 14, tzinfo=UTC),
            adjustment_state="split_adjusted",
        ),
    ]
    snap = MarketSnapshot(
        symbol="AAPL",
        bars=bars,
        provider="fixture",
        retrieved_at=datetime(2026, 9, 14, tzinfo=UTC),
        as_of=datetime(2026, 9, 14, tzinfo=UTC),
        latest_completed_session=date(2026, 9, 11),
        content_hash="a" * 64,
    )
    with pytest.raises(ValueError, match="INVALID_PRICE_SERIES: duplicate session"):
        calculate_metrics(snap)


@pytest.mark.parametrize("obs_count", [0, 1, 2, 6, 20])
def test_boundary_observations_return_safe_none_for_unavailable_windows(obs_count: int) -> None:
    closes = [100.0 + i for i in range(obs_count)]
    metrics = calculate_metrics(snapshot(closes))
    values = {m.key: m.value for m in metrics}

    assert values["price_observation_count"] == obs_count

    if obs_count < 2:
        assert values["return_1_session"] is None
    else:
        assert values["return_1_session"] is not None

    if obs_count < 6:
        assert values["return_5_sessions"] is None
    else:
        assert values["return_5_sessions"] is not None

    if obs_count < 21:
        assert values["return_20_sessions"] is None
        assert values["annualized_volatility_20"] is None
        assert values["max_drawdown_20"] is None

    if obs_count < 20:
        assert values["average_dollar_volume_20"] is None
    else:
        assert values["average_dollar_volume_20"] is not None


def test_drawdown_with_real_decline() -> None:
    # 10 bars at 100, peak at 120, then drop to 90 (drawdown = 90 / 120 - 1 = -0.25)
    closes = [100.0] * 10 + [120.0] + [110.0] * 5 + [90.0] + [95.0] * 4
    metrics = calculate_metrics(snapshot(closes))
    values = {m.key: m.value for m in metrics}
    assert values["max_drawdown_20"] == pytest.approx(-0.25)


def test_valid_market_snapshot_fixture_loads_and_calculates() -> None:
    from pathlib import Path

    fixture_path = Path(__file__).parent.parent / "fixtures" / "market_snapshot_valid.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = f.read()
    snap = MarketSnapshot.model_validate_json(data)
    metrics = calculate_metrics(snap)
    values = {m.key: m.value for m in metrics}
    assert values["price_observation_count"] == 21
    assert values["return_20_sessions"] is not None

