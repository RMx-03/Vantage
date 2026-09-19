from collections.abc import Mapping
from datetime import datetime
import math
from statistics import stdev
from typing import Literal

from app.domain.research import (
    ComponentQuality,
    MarketSnapshot,
    NewsSnapshot,
    ResearchMetric,
)
from app.services.quality import worse_component_quality

METRICS_VERSION: Literal["eod-metrics-v2"] = "eod-metrics-v2"

METRIC_DEFINITIONS: dict[
    str, tuple[str, Literal["ratio", "percent", "usd", "count", "sessions"], int | None]
] = {
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
}


def build_metric_registry(
    *,
    as_of: datetime,
    values: Mapping[str, float | int | None],
    qualities: Mapping[str, ComponentQuality],
) -> list[ResearchMetric]:
    return [
        ResearchMetric(
            key=key,
            label=label,
            value=values.get(key),
            unit=unit,
            window_sessions=window,
            as_of=as_of,
            calculation_version=METRICS_VERSION,
            quality=qualities[key],
        )
        for key, (label, unit, window) in METRIC_DEFINITIONS.items()
    ]


def calculate_metrics(
    snapshot: MarketSnapshot, news: NewsSnapshot
) -> list[ResearchMetric]:
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

    return build_metric_registry(
        as_of=snapshot.as_of,
        values=values,
        qualities=qualities,
    )
