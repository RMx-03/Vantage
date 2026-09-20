from datetime import UTC, date, datetime

import pytest

from app.domain.research import (
    ComponentQuality,
    DailyBar,
    MarketSnapshot,
    NewsItem,
    NewsSnapshot,
)
from app.services.snapshots import combined_snapshot_hash


def _snapshots() -> tuple[MarketSnapshot, NewsSnapshot]:
    now = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
    market = MarketSnapshot(
        symbol="AAPL",
        bars=[
            DailyBar(
                symbol="AAPL",
                session_date=date(2026, 9, 14),
                open=100,
                high=101,
                low=99,
                close=100,
                adjusted_close=100,
                volume=1000,
                currency="USD",
                provider="market",
                retrieved_at=now,
                adjustment_state="split_and_dividend_adjusted",
            )
        ],
        provider="market",
        retrieved_at=now,
        as_of=now,
        latest_completed_session=date(2026, 9, 14),
        content_hash="a" * 64,
    )
    items = [
        NewsItem(
            evidence_id="b",
            provider="news",
            publisher="Reuters",
            title="Second",
            retrieved_at=now,
            content_hash="b" * 64,
        ),
        NewsItem(
            evidence_id="a",
            provider="news",
            publisher="AP",
            title="First",
            retrieved_at=now,
            content_hash="c" * 64,
        ),
    ]
    news = NewsSnapshot(
        symbol="AAPL",
        items=items,
        provider="news",
        retrieved_at=now,
        quality=ComponentQuality.FRESH,
    )
    return market, news


def test_combined_snapshot_hash_is_order_independent_and_content_sensitive() -> None:
    market, news = _snapshots()
    expected = combined_snapshot_hash(market, news)
    reordered = news.model_copy(update={"items": list(reversed(news.items))})
    mutated = news.model_copy(
        update={
            "items": [
                news.items[0].model_copy(update={"title": "Changed"}),
                news.items[1],
            ]
        }
    )
    assert combined_snapshot_hash(market, reordered) == expected
    assert combined_snapshot_hash(market, mutated) != expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quality", ComponentQuality.PARTIAL),
        ("volume_quality", ComponentQuality.PARTIAL),
        ("error_code", "INVALID_PRICE_SERIES"),
        ("missing_value_count", 1),
        ("duplicate_session_count", 1),
    ],
)
def test_combined_snapshot_hash_includes_market_diagnostics(
    field: str, value: ComponentQuality | str | int
) -> None:
    market, news = _snapshots()

    degraded = market.model_copy(update={field: value})

    assert combined_snapshot_hash(degraded, news) != combined_snapshot_hash(
        market, news
    )
