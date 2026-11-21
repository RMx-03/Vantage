import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import ValidationError
import pytest

from app.domain.research import (
    ComponentQuality,
    CrossCheckClose,
    DailyBar,
    FilingsSnapshot,
    FundamentalsSnapshot,
    MacroObservation,
    MacroSnapshot,
    MarketSnapshot,
    NewsItem,
    NewsSnapshot,
    PriceCrossCheckSnapshot,
    ResearchMetric,
)
from app.services.metrics import calculate_metrics
from app.services.run_inputs import RunInputs


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


def news_snapshot() -> NewsSnapshot:
    retrieved_at = datetime(2026, 9, 14, tzinfo=UTC)
    return NewsSnapshot(
        symbol="AAPL",
        items=[
            NewsItem(
                evidence_id="news-1",
                provider="fixture",
                publisher="Reuters",
                title="First item",
                retrieved_at=retrieved_at,
            ),
            NewsItem(
                evidence_id="news-2",
                provider="fixture",
                publisher="Reuters",
                title="Second item",
                retrieved_at=retrieved_at,
            ),
        ],
        provider="fixture",
        retrieved_at=retrieved_at,
        quality=ComponentQuality.FRESH,
    )


def missing_news_snapshot() -> NewsSnapshot:
    return NewsSnapshot(
        symbol="AAPL",
        items=[],
        provider="fixture",
        retrieved_at=datetime(2026, 9, 14, tzinfo=UTC),
        quality=ComponentQuality.MISSING,
    )


def test_returns_drawdown_and_liquidity_are_golden() -> None:
    values = {
        m.key: m.value
        for m in calculate_metrics(snapshot([100.0] * 20 + [110.0]), news_snapshot())
    }
    assert values["return_1_session"] == pytest.approx(0.10)
    assert values["return_5_sessions"] == pytest.approx(0.10)
    assert values["return_20_sessions"] == pytest.approx(0.10)
    assert values["max_drawdown_20"] == pytest.approx(0.0)
    assert values["average_dollar_volume_20"] == pytest.approx(100_500_000.0)
    assert values["price_observation_count"] == 21
    assert values["price_missing_value_count"] == 0
    assert values["price_duplicate_session_count"] == 0
    assert values["news_item_count"] == 2
    assert values["news_publisher_count"] == 1


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_close_never_serializes_as_zero(bad: float) -> None:
    with pytest.raises(ValueError, match="INVALID_PRICE_SERIES"):
        calculate_metrics(snapshot([100.0] * 20 + [bad]), news_snapshot())


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
        calculate_metrics(snap, news_snapshot())


@pytest.mark.parametrize("obs_count", [0, 1, 2, 6, 20])
def test_boundary_observations_return_safe_none_for_unavailable_windows(
    obs_count: int,
) -> None:
    closes = [100.0 + i for i in range(obs_count)]
    metrics = calculate_metrics(snapshot(closes), news_snapshot())
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
    metrics = calculate_metrics(snapshot(closes), news_snapshot())
    values = {m.key: m.value for m in metrics}
    assert values["max_drawdown_20"] == pytest.approx(-0.25)


def test_valid_market_snapshot_fixture_loads_and_calculates() -> None:
    from pathlib import Path

    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "market_snapshot_valid.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = f.read()
    snap = MarketSnapshot.model_validate_json(data)
    metrics = calculate_metrics(snap, news_snapshot())
    values = {m.key: m.value for m in metrics}
    assert values["price_observation_count"] == 21
    assert values["return_20_sessions"] is not None


@pytest.mark.parametrize(
    "quality",
    [
        ComponentQuality.PARTIAL,
        ComponentQuality.STALE,
        ComponentQuality.MISSING,
        ComponentQuality.FAILED,
    ],
)
def test_price_metrics_inherit_market_quality(quality: ComponentQuality) -> None:
    market = snapshot([100.0] * 21).model_copy(update={"quality": quality})

    metrics = {
        metric.key: metric for metric in calculate_metrics(market, news_snapshot())
    }

    for key in (
        "return_1_session",
        "return_5_sessions",
        "return_20_sessions",
        "annualized_volatility_20",
        "max_drawdown_20",
        "price_observation_count",
        "price_missing_value_count",
        "price_duplicate_session_count",
    ):
        assert metrics[key].quality == quality


def test_incomplete_price_window_degrades_metric_quality() -> None:
    metrics = {
        metric.key: metric
        for metric in calculate_metrics(snapshot([100.0] * 20), news_snapshot())
    }

    assert metrics["return_20_sessions"].value is None
    assert metrics["return_20_sessions"].quality == ComponentQuality.PARTIAL
    assert metrics["price_observation_count"].quality == ComponentQuality.FRESH


@pytest.mark.parametrize(
    ("market_quality", "volume_quality", "expected"),
    [
        (
            ComponentQuality.FRESH,
            ComponentQuality.PARTIAL,
            ComponentQuality.PARTIAL,
        ),
        (
            ComponentQuality.PARTIAL,
            ComponentQuality.STALE,
            ComponentQuality.STALE,
        ),
        (
            ComponentQuality.STALE,
            ComponentQuality.MISSING,
            ComponentQuality.MISSING,
        ),
        (
            ComponentQuality.MISSING,
            ComponentQuality.FAILED,
            ComponentQuality.FAILED,
        ),
        (
            ComponentQuality.PARTIAL,
            ComponentQuality.FRESH,
            ComponentQuality.PARTIAL,
        ),
        (
            ComponentQuality.STALE,
            ComponentQuality.PARTIAL,
            ComponentQuality.STALE,
        ),
        (
            ComponentQuality.MISSING,
            ComponentQuality.STALE,
            ComponentQuality.MISSING,
        ),
        (
            ComponentQuality.FAILED,
            ComponentQuality.MISSING,
            ComponentQuality.FAILED,
        ),
    ],
)
def test_average_dollar_volume_uses_worse_source_quality(
    market_quality: ComponentQuality,
    volume_quality: ComponentQuality,
    expected: ComponentQuality,
) -> None:
    market = snapshot([100.0] * 21).model_copy(
        update={"quality": market_quality, "volume_quality": volume_quality}
    )

    metrics = {
        metric.key: metric for metric in calculate_metrics(market, news_snapshot())
    }

    assert metrics["average_dollar_volume_20"].quality == expected


def test_news_counts_inherit_missing_quality_even_when_zero() -> None:
    metrics = {
        metric.key: metric
        for metric in calculate_metrics(snapshot([100.0] * 21), missing_news_snapshot())
    }

    assert metrics["news_item_count"].value == 0
    assert metrics["news_item_count"].quality == ComponentQuality.MISSING
    assert metrics["news_publisher_count"].value == 0
    assert metrics["news_publisher_count"].quality == ComponentQuality.MISSING


def test_metric_order_is_stable() -> None:
    metrics = calculate_metrics(snapshot([100.0] * 21), news_snapshot())

    assert [metric.key for metric in metrics][:11] == [
        "return_1_session",
        "return_5_sessions",
        "return_20_sessions",
        "annualized_volatility_20",
        "max_drawdown_20",
        "average_dollar_volume_20",
        "price_observation_count",
        "price_missing_value_count",
        "price_duplicate_session_count",
        "news_item_count",
        "news_publisher_count",
    ]
    assert [metric.key for metric in metrics][11:] == NEW_KEYS


def test_metrics_use_v3_calculation_contract() -> None:
    metrics = calculate_metrics(snapshot([100.0] * 21), news_snapshot())

    assert {metric.calculation_version for metric in metrics} == {"eod-metrics-v3"}


NEW_KEYS = [
    "excess_return_5_vs_spy",
    "excess_return_20_vs_spy",
    "excess_return_20_vs_sector",
    "revenue_growth_fy_yoy",
    "net_margin_fy",
    "us10y_yield",
    "fed_funds_rate",
    "yield_curve_10y_2y",
    "vix_close",
    "filing_count_30d",
    "insider_filing_count_90d",
]

UTC_NOW = datetime(2026, 9, 14, tzinfo=UTC)


def by_key(metrics: list[ResearchMetric]) -> dict[str, ResearchMetric]:
    return {metric.key: metric for metric in metrics}


def bars_for(
    closes: list[float], symbol: str = "SPY", skip_last: int = 0
) -> list[DailyBar]:
    bars = snapshot(closes).bars
    if skip_last:
        bars = bars[:-skip_last]
    return [bar.model_copy(update={"symbol": symbol}) for bar in bars]


def with_context(market: MarketSnapshot, **context: list[DailyBar]) -> MarketSnapshot:
    return market.model_copy(update={"context_bars": context})


def configured(**kwargs: Any) -> RunInputs:
    return RunInputs(not_configured=frozenset(), **kwargs)


def test_without_inputs_new_metrics_are_missing_and_no_crosscheck() -> None:
    metrics = calculate_metrics(snapshot([100.0] * 20 + [110.0]), news_snapshot())
    values = by_key(metrics)

    assert len(metrics) == 22
    assert "price_crosscheck_max_deviation" not in values
    assert values["return_20_sessions"].value == pytest.approx(0.10)
    for key in NEW_KEYS:
        assert values[key].value is None
        assert values[key].quality == ComponentQuality.MISSING
        assert values[key].as_of == datetime(2026, 9, 14, tzinfo=UTC)
        assert values[key].calculation_version == "eod-metrics-v3"


def test_new_metric_definitions() -> None:
    values = by_key(calculate_metrics(snapshot([100.0] * 21), news_snapshot()))

    expected = {
        "excess_return_5_vs_spy": ("5-session excess return vs SPY", "ratio", 5),
        "excess_return_20_vs_spy": ("20-session excess return vs SPY", "ratio", 20),
        "excess_return_20_vs_sector": (
            "20-session excess return vs sector ETF",
            "ratio",
            20,
        ),
        "revenue_growth_fy_yoy": ("Fiscal-year revenue growth", "ratio", None),
        "net_margin_fy": ("Fiscal-year net margin", "ratio", None),
        "us10y_yield": ("US 10-year Treasury yield", "percent", None),
        "fed_funds_rate": ("Effective federal funds rate", "percent", None),
        "yield_curve_10y_2y": (
            "10-year minus 2-year Treasury spread",
            "percent",
            None,
        ),
        "vix_close": ("VIX close (Cboe)", "index", None),
        "filing_count_30d": ("SEC filings in the last 30 days", "count", None),
        "insider_filing_count_90d": (
            "Form 4 filings in the last 90 days",
            "count",
            None,
        ),
    }
    for key, (label, unit, window) in expected.items():
        assert values[key].label == label
        assert values[key].unit == unit
        assert values[key].window_sessions == window


def test_excess_returns_against_spy_and_sector() -> None:
    market = with_context(
        snapshot([100.0] * 20 + [110.0]),
        SPY=bars_for([100.0] * 20 + [104.0]),
        XLK=bars_for([100.0] * 20 + [101.0], "XLK"),
    )
    values = by_key(
        calculate_metrics(market, news_snapshot(), configured(sector_etf="XLK"))
    )

    assert values["excess_return_20_vs_spy"].value == pytest.approx(0.06)
    assert values["excess_return_5_vs_spy"].value == pytest.approx(0.06)
    assert values["excess_return_20_vs_sector"].value == pytest.approx(0.09)
    assert (
        values["excess_return_20_vs_sector"].label == "20-session excess return vs XLK"
    )
    assert values["excess_return_20_vs_spy"].quality == ComponentQuality.FRESH
    assert values["excess_return_20_vs_spy"].as_of == market.as_of


def test_sector_metric_missing_without_sector_etf() -> None:
    market = with_context(
        snapshot([100.0] * 20 + [110.0]), SPY=bars_for([100.0] * 20 + [104.0])
    )
    values = by_key(calculate_metrics(market, news_snapshot(), configured()))

    assert values["excess_return_20_vs_sector"].value is None
    assert values["excess_return_20_vs_sector"].quality == ComponentQuality.MISSING
    assert values["excess_return_20_vs_sector"].label.endswith("vs sector ETF")


def test_context_ending_one_session_earlier_gives_missing() -> None:
    market = with_context(
        snapshot([100.0] * 20 + [110.0]),
        SPY=bars_for([100.0] * 20 + [104.0], skip_last=1),
        XLK=bars_for([100.0] * 20 + [104.0], "XLK", skip_last=1),
    )
    values = by_key(
        calculate_metrics(market, news_snapshot(), configured(sector_etf="XLK"))
    )

    for key in (
        "excess_return_5_vs_spy",
        "excess_return_20_vs_spy",
        "excess_return_20_vs_sector",
    ):
        assert values[key].value is None
        assert values[key].quality == ComponentQuality.MISSING


def test_relative_metrics_inherit_stale_market_quality() -> None:
    market = with_context(
        snapshot([100.0] * 20 + [110.0]).model_copy(
            update={"quality": ComponentQuality.STALE}
        ),
        SPY=bars_for([100.0] * 20 + [104.0]),
    )
    values = by_key(calculate_metrics(market, news_snapshot(), configured()))

    assert values["excess_return_20_vs_spy"].value == pytest.approx(0.06)
    assert values["excess_return_20_vs_spy"].quality == ComponentQuality.STALE


def test_too_few_primary_bars_gives_none() -> None:
    market = with_context(
        snapshot([100.0] * 5 + [110.0]), SPY=bars_for([100.0] * 5 + [104.0])
    )
    values = by_key(calculate_metrics(market, news_snapshot(), configured()))

    assert values["excess_return_5_vs_spy"].value == pytest.approx(0.06)
    assert values["excess_return_20_vs_spy"].value is None


def fundamentals(**kwargs: Any) -> FundamentalsSnapshot:
    data: dict[str, Any] = {
        "symbol": "AAPL",
        "provider": "sec-edgar",
        "retrieved_at": UTC_NOW,
        "quality": ComponentQuality.FRESH,
        "fiscal_year": 2025,
        "period_end": date(2025, 9, 27),
        "revenue": 440.0,
        "prior_revenue": 400.0,
        "net_income": 88.0,
    }
    data.update(kwargs)
    return FundamentalsSnapshot(**data)


def test_fundamentals_metrics_use_period_end_as_of() -> None:
    values = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(fundamentals=fundamentals()),
        )
    )

    growth = values["revenue_growth_fy_yoy"]
    assert growth.value == pytest.approx(0.10)
    assert growth.quality == ComponentQuality.FRESH
    assert growth.as_of == datetime(2025, 9, 27, tzinfo=UTC)
    assert values["net_margin_fy"].value == pytest.approx(0.2)
    assert values["net_margin_fy"].as_of == datetime(2025, 9, 27, tzinfo=UTC)


@pytest.mark.parametrize("prior", [0.0, None])
def test_revenue_growth_needs_positive_prior_revenue(prior: float | None) -> None:
    values = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(fundamentals=fundamentals(prior_revenue=prior)),
        )
    )

    assert values["revenue_growth_fy_yoy"].value is None
    assert values["revenue_growth_fy_yoy"].quality == ComponentQuality.MISSING
    assert values["net_margin_fy"].value == pytest.approx(0.2)


def test_net_margin_needs_positive_revenue_and_can_be_negative() -> None:
    zero = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(fundamentals=fundamentals(revenue=0.0)),
        )
    )
    assert zero["net_margin_fy"].value is None
    assert zero["net_margin_fy"].quality == ComponentQuality.MISSING

    loss = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(fundamentals=fundamentals(net_income=-44.0)),
        )
    )
    assert loss["net_margin_fy"].value == pytest.approx(-0.1)


def macro(*observations: MacroObservation) -> MacroSnapshot:
    return MacroSnapshot(
        provider="fred",
        retrieved_at=UTC_NOW,
        quality=ComponentQuality.FRESH,
        observations=list(observations),
    )


def test_macro_metrics_use_observation_quality_and_date() -> None:
    inputs = configured(
        macro=macro(
            MacroObservation(
                series_id="DGS10",
                value=4.25,
                observation_date=date(2026, 9, 11),
                quality=ComponentQuality.FRESH,
            ),
            MacroObservation(
                series_id="DFF",
                value=4.33,
                observation_date=date(2026, 9, 1),
                quality=ComponentQuality.STALE,
            ),
            MacroObservation(
                series_id="T10Y2Y",
                value=None,
                observation_date=None,
                quality=ComponentQuality.MISSING,
            ),
        )
    )
    values = by_key(calculate_metrics(snapshot([100.0] * 21), news_snapshot(), inputs))

    assert values["us10y_yield"].value == pytest.approx(4.25)
    assert values["us10y_yield"].quality == ComponentQuality.FRESH
    assert values["us10y_yield"].as_of == datetime(2026, 9, 11, tzinfo=UTC)
    assert values["fed_funds_rate"].quality == ComponentQuality.STALE
    assert values["fed_funds_rate"].as_of == datetime(2026, 9, 1, tzinfo=UTC)
    assert values["yield_curve_10y_2y"].value is None
    assert values["yield_curve_10y_2y"].quality == ComponentQuality.MISSING
    assert values["vix_close"].value is None
    assert values["vix_close"].quality == ComponentQuality.MISSING
    assert values["vix_close"].as_of == datetime(2026, 9, 14, tzinfo=UTC)


def filings_snapshot(
    quality: ComponentQuality = ComponentQuality.FRESH,
    items: int = 0,
    insiders: int = 0,
) -> FilingsSnapshot:
    return FilingsSnapshot(
        symbol="AAPL",
        items=[
            NewsItem(
                evidence_id=f"filing-{i}",
                provider="sec-edgar",
                title="8-K",
                retrieved_at=UTC_NOW,
                source_type="filing",
            )
            for i in range(items)
        ],
        provider="sec-edgar",
        retrieved_at=UTC_NOW,
        quality=quality,
        insider_filing_count=insiders,
    )


def test_fresh_filings_with_no_items_gives_zero_counts() -> None:
    values = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(filings=filings_snapshot()),
        )
    )

    assert values["filing_count_30d"].value == 0
    assert values["filing_count_30d"].quality == ComponentQuality.FRESH
    assert values["insider_filing_count_90d"].value == 0
    assert values["insider_filing_count_90d"].quality == ComponentQuality.FRESH


def test_filing_counts_count_filing_items_only() -> None:
    snap = filings_snapshot(items=3, insiders=7)
    snap.items.append(
        NewsItem(
            evidence_id="insider-1",
            provider="sec-edgar",
            title="Form 4",
            retrieved_at=UTC_NOW,
            source_type="insider_transaction",
        )
    )
    values = by_key(
        calculate_metrics(
            snapshot([100.0] * 21), news_snapshot(), configured(filings=snap)
        )
    )

    assert values["filing_count_30d"].value == 3
    assert values["insider_filing_count_90d"].value == 7


def test_failed_filings_gives_missing_counts() -> None:
    values = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(failed={"filings": "PROVIDER_TIMEOUT"}),
        )
    )

    for key in ("filing_count_30d", "insider_filing_count_90d"):
        assert values[key].value is None
        assert values[key].quality == ComponentQuality.MISSING


def crosscheck(closes: list[float], skip_dates: int = 0) -> PriceCrossCheckSnapshot:
    bars = snapshot([100.0] * 21).bars
    return PriceCrossCheckSnapshot(
        symbol="AAPL",
        provider="tiingo",
        retrieved_at=UTC_NOW,
        quality=ComponentQuality.FRESH,
        closes=[
            CrossCheckClose(
                session_date=bar.session_date + timedelta(days=skip_dates),
                adjusted_close=close,
            )
            for bar, close in zip(bars, closes, strict=True)
        ],
    )


def test_crosscheck_metric_absent_when_not_configured() -> None:
    values = by_key(calculate_metrics(snapshot([100.0] * 21), news_snapshot()))

    assert "price_crosscheck_max_deviation" not in values


def test_crosscheck_max_deviation() -> None:
    other = [100.0] * 20 + [100.0 / 1.012]
    values = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(crosscheck=crosscheck(other)),
        )
    )

    metric = values["price_crosscheck_max_deviation"]
    assert metric.value == pytest.approx(0.012)
    assert metric.unit == "ratio"
    assert metric.quality == ComponentQuality.FRESH
    assert list(values)[-1] == "price_crosscheck_max_deviation"


def test_crosscheck_without_shared_session_gives_missing() -> None:
    values = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(crosscheck=crosscheck([100.0] * 21, skip_dates=100)),
        )
    )

    metric = values["price_crosscheck_max_deviation"]
    assert metric.value is None
    assert metric.quality == ComponentQuality.MISSING


def test_crosscheck_failed_gives_missing_but_present() -> None:
    values = by_key(
        calculate_metrics(
            snapshot([100.0] * 21),
            news_snapshot(),
            configured(failed={"crosscheck": "PROVIDER_TIMEOUT"}),
        )
    )

    assert values["price_crosscheck_max_deviation"].value is None
    assert values["price_crosscheck_max_deviation"].quality == ComponentQuality.MISSING
