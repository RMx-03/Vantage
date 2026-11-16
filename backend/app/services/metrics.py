from collections.abc import Mapping
from datetime import UTC, date, datetime, time
import math
from statistics import stdev
from typing import Literal

from app.domain.research import (
    ComponentQuality,
    DailyBar,
    MacroObservation,
    MarketSnapshot,
    NewsSnapshot,
    ResearchMetric,
    RoleQuality,
)
from app.services.quality import worse_component_quality
from app.services.run_inputs import RunInputs

METRICS_VERSION: Literal["eod-metrics-v3"] = "eod-metrics-v3"

MetricUnit = Literal["ratio", "percent", "usd", "count", "sessions", "index"]

SECTOR_LABEL_TEMPLATE = "20-session excess return vs {}"
SECTOR_LABEL_FALLBACK = "sector ETF"

# One place for key, label, unit and window of every metric, in output order.
METRIC_DEFINITIONS: dict[str, tuple[str, MetricUnit, int | None]] = {
    "return_1_session": ("1-session return", "ratio", 1),
    "return_5_sessions": ("5-session return", "ratio", 5),
    "return_20_sessions": ("20-session return", "ratio", 20),
    "annualized_volatility_20": ("20-session annualized volatility", "ratio", 20),
    "max_drawdown_20": ("20-session maximum drawdown", "ratio", 20),
    "average_dollar_volume_20": ("20-session average dollar volume", "usd", 20),
    "price_observation_count": ("Accepted price observations", "count", None),
    "price_missing_value_count": ("Rejected missing price values", "count", None),
    "price_duplicate_session_count": ("Duplicate price sessions", "count", None),
    "news_item_count": ("Accepted news items", "count", None),
    "news_publisher_count": ("Distinct news publishers", "count", None),
    "excess_return_5_vs_spy": ("5-session excess return vs SPY", "ratio", 5),
    "excess_return_20_vs_spy": ("20-session excess return vs SPY", "ratio", 20),
    "excess_return_20_vs_sector": (
        SECTOR_LABEL_TEMPLATE.format(SECTOR_LABEL_FALLBACK),
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
    "insider_filing_count_90d": ("Form 4 filings in the last 90 days", "count", None),
    "price_crosscheck_max_deviation": (
        "Largest adjusted-close gap vs the cross-check source",
        "ratio",
        None,
    ),
}

MACRO_SERIES: dict[str, str] = {
    "us10y_yield": "DGS10",
    "fed_funds_rate": "DFF",
    "yield_curve_10y_2y": "T10Y2Y",
    "vix_close": "VIXCLS",
}

_UNUSABLE_ROLE = (RoleQuality.NOT_CONFIGURED, RoleQuality.FAILED)


def build_metric_registry(
    *,
    as_of: datetime,
    values: Mapping[str, float | int | None],
    qualities: Mapping[str, ComponentQuality],
    as_ofs: Mapping[str, datetime] | None = None,
    labels: Mapping[str, str] | None = None,
) -> list[ResearchMetric]:
    """Build a metric for every key in `values`, in definition order."""
    return [
        ResearchMetric(
            key=key,
            label=(labels or {}).get(key, label),
            value=values[key],
            unit=unit,
            window_sessions=window,
            as_of=(as_ofs or {}).get(key, as_of),
            calculation_version=METRICS_VERSION,
            quality=qualities[key],
        )
        for key, (label, unit, window) in METRIC_DEFINITIONS.items()
        if key in values
    ]


def _midnight_utc(day: date | None) -> datetime | None:
    return datetime.combine(day, time.min, tzinfo=UTC) if day is not None else None


def _excess_return(
    primary: list[DailyBar], context: list[DailyBar] | None, window: int
) -> float | None:
    """Primary return minus the context return over the primary's last sessions.

    The context series must have a bar on both the first and the last of those
    sessions, otherwise the value is unavailable rather than approximated.
    """
    if context is None or len(primary) < window + 1:
        return None
    first, last = primary[-1 - window], primary[-1]
    by_date = {bar.session_date: bar for bar in context}
    context_first = by_date.get(first.session_date)
    context_last = by_date.get(last.session_date)
    if context_first is None or context_last is None:
        return None
    return (last.adjusted_close / first.adjusted_close - 1) - (
        context_last.adjusted_close / context_first.adjusted_close - 1
    )


def calculate_metrics(
    snapshot: MarketSnapshot,
    news: NewsSnapshot,
    inputs: RunInputs | None = None,
) -> list[ResearchMetric]:
    inputs = inputs if inputs is not None else RunInputs()
    bars = sorted(snapshot.bars, key=lambda bar: bar.session_date)
    if len({bar.session_date for bar in bars}) != len(bars):
        raise ValueError("INVALID_PRICE_SERIES: duplicate session")
    if any(
        bar.adjusted_close <= 0 or not math.isfinite(bar.adjusted_close) for bar in bars
    ):
        raise ValueError("INVALID_PRICE_SERIES: close")

    closes = [bar.adjusted_close for bar in bars]

    def simple_return(window: int) -> float | None:
        if len(closes) >= window + 1:
            return closes[-1] / closes[-1 - window] - 1
        return None

    # Volatility over 20 log return steps requires 21 closes
    log_returns = (
        [
            math.log(closes[i] / closes[i - 1])
            for i in range(max(1, len(closes) - 20), len(closes))
        ]
        if len(closes) >= 2
        else []
    )
    vol = stdev(log_returns) * math.sqrt(252) if len(log_returns) == 20 else None

    # Drawdown over the last 21 closes
    window = closes[-21:]
    if len(window) == 21:
        peak = window[0]
        drawdowns: list[float] = []
        for close in window:
            peak = max(peak, close)
            drawdowns.append(close / peak - 1)
        max_dd: float | None = min(drawdowns)
    else:
        max_dd = None

    avg_dollar_vol = (
        sum(bar.close * bar.volume for bar in bars[-20:]) / 20
        if len(bars) >= 20
        else None
    )

    values: dict[str, float | int | None] = {
        "return_1_session": simple_return(1),
        "return_5_sessions": simple_return(5),
        "return_20_sessions": simple_return(20),
        "annualized_volatility_20": vol,
        "max_drawdown_20": max_dd,
        "average_dollar_volume_20": avg_dollar_vol,
        "price_observation_count": len(bars),
        "price_missing_value_count": snapshot.missing_value_count,
        "price_duplicate_session_count": snapshot.duplicate_session_count,
        "news_item_count": len(news.items),
        "news_publisher_count": len(
            {item.publisher.strip().casefold() for item in news.items if item.publisher}
        ),
    }

    qualities = {
        key: worse_component_quality(
            snapshot.quality,
            ComponentQuality.FRESH
            if values[key] is not None
            else ComponentQuality.PARTIAL,
        )
        for key in (
            "return_1_session",
            "return_5_sessions",
            "return_20_sessions",
            "annualized_volatility_20",
            "max_drawdown_20",
        )
    }
    qualities["average_dollar_volume_20"] = worse_component_quality(
        snapshot.quality,
        snapshot.volume_quality,
        ComponentQuality.FRESH
        if values["average_dollar_volume_20"] is not None
        else ComponentQuality.PARTIAL,
    )
    qualities.update(
        {
            "price_observation_count": snapshot.quality,
            "price_missing_value_count": snapshot.quality,
            "price_duplicate_session_count": snapshot.quality,
            "news_item_count": news.quality,
            "news_publisher_count": news.quality,
        }
    )

    as_ofs: dict[str, datetime] = {}
    labels: dict[str, str] = {}

    def present(key: str, quality: ComponentQuality) -> None:
        qualities[key] = (
            quality if values[key] is not None else ComponentQuality.MISSING
        )

    # Relative returns.
    sector_series = (
        snapshot.context_bars.get(inputs.sector_etf) if inputs.sector_etf else None
    )
    spy_series = snapshot.context_bars.get("SPY")
    values["excess_return_5_vs_spy"] = _excess_return(bars, spy_series, 5)
    values["excess_return_20_vs_spy"] = _excess_return(bars, spy_series, 20)
    values["excess_return_20_vs_sector"] = _excess_return(bars, sector_series, 20)
    labels["excess_return_20_vs_sector"] = SECTOR_LABEL_TEMPLATE.format(
        inputs.sector_etf or SECTOR_LABEL_FALLBACK
    )
    for key in (
        "excess_return_5_vs_spy",
        "excess_return_20_vs_spy",
        "excess_return_20_vs_sector",
    ):
        present(key, snapshot.quality)

    # Fiscal-year fundamentals.
    fundamentals = (
        inputs.fundamentals
        if inputs.role_quality("fundamentals") not in _UNUSABLE_ROLE
        else None
    )
    revenue = fundamentals.revenue if fundamentals else None
    prior_revenue = fundamentals.prior_revenue if fundamentals else None
    net_income = fundamentals.net_income if fundamentals else None
    values["revenue_growth_fy_yoy"] = (
        revenue / prior_revenue - 1
        if revenue is not None and prior_revenue is not None and prior_revenue > 0
        else None
    )
    values["net_margin_fy"] = (
        net_income / revenue
        if net_income is not None and revenue is not None and revenue > 0
        else None
    )
    period_end = _midnight_utc(fundamentals.period_end if fundamentals else None)
    for key in ("revenue_growth_fy_yoy", "net_margin_fy"):
        present(key, ComponentQuality.FRESH)
        if period_end is not None:
            as_ofs[key] = period_end

    # Macro levels, each with its own observation date and quality.
    observations: dict[str, MacroObservation] = {}
    if inputs.macro is not None and inputs.role_quality("macro") not in _UNUSABLE_ROLE:
        observations = {obs.series_id: obs for obs in inputs.macro.observations}
    for key, series_id in MACRO_SERIES.items():
        observation = observations.get(series_id)
        if observation is None or observation.value is None:
            values[key] = None
            qualities[key] = ComponentQuality.MISSING
            continue
        values[key] = observation.value
        qualities[key] = observation.quality
        observed = _midnight_utc(observation.observation_date)
        if observed is not None:
            as_ofs[key] = observed

    # Filing counts.
    filings = (
        inputs.filings
        if inputs.role_quality("filings") not in (*_UNUSABLE_ROLE, RoleQuality.MISSING)
        else None
    )
    values["filing_count_30d"] = (
        sum(1 for item in filings.items if item.source_type == "filing")
        if filings is not None
        else None
    )
    values["insider_filing_count_90d"] = (
        filings.insider_filing_count if filings is not None else None
    )
    for key in ("filing_count_30d", "insider_filing_count_90d"):
        present(key, ComponentQuality.FRESH)

    # Price cross-check, listed only when the role is configured.
    if "crosscheck" not in inputs.not_configured:
        deviation: float | None = None
        crosscheck = (
            inputs.crosscheck
            if inputs.role_quality("crosscheck") not in _UNUSABLE_ROLE
            else None
        )
        if crosscheck is not None:
            reference = {c.session_date: c.adjusted_close for c in crosscheck.closes}
            gaps = [
                abs(bar.adjusted_close - reference[bar.session_date])
                / reference[bar.session_date]
                for bar in bars
                if bar.session_date in reference
            ]
            deviation = max(gaps) if gaps else None
        values["price_crosscheck_max_deviation"] = deviation
        present(
            "price_crosscheck_max_deviation",
            crosscheck.quality if crosscheck is not None else ComponentQuality.MISSING,
        )

    return build_metric_registry(
        as_of=snapshot.as_of,
        values=values,
        qualities=qualities,
        as_ofs=as_ofs,
        labels=labels,
    )
