from datetime import UTC, date, datetime

import pytest

from app.domain.research import (
    ComponentQuality,
    DailyBar,
    EvidenceDetails,
    FundamentalsSnapshot,
    MacroObservation,
    MacroSnapshot,
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


def _bar(symbol: str, day: int) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        session_date=date(2026, 9, day),
        open=10,
        high=11,
        low=9,
        close=10,
        adjusted_close=10,
        volume=5,
        currency="USD",
        provider="market",
        retrieved_at=datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
        adjustment_state="split_and_dividend_adjusted",
    )


def _fundamentals(retrieved_at: datetime) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        symbol="AAPL",
        provider="sec",
        retrieved_at=retrieved_at,
        quality=ComponentQuality.FRESH,
        revenue=100.0,
    )


def _macro(retrieved_at: datetime) -> MacroSnapshot:
    return MacroSnapshot(
        provider="fred",
        retrieved_at=retrieved_at,
        quality=ComponentQuality.FRESH,
        observations=[
            MacroObservation(
                series_id="DGS10",
                value=4.0,
                observation_date=date(2026, 9, 12),
                quality=ComponentQuality.FRESH,
            )
        ],
    )


def test_existing_shape_hash_is_unchanged() -> None:
    market, news = _snapshots()
    assert (
        combined_snapshot_hash(market, news)
        == "b7366d2496ff18eabfcbc4c3fc375a06ef541bcdc8f136ed7fd8f9cb20c3cc7c"
    )


def test_context_bars_change_the_hash() -> None:
    market, news = _snapshots()
    with_ctx = market.model_copy(update={"context_bars": {"SPY": [_bar("SPY", 14)]}})
    assert combined_snapshot_hash(with_ctx, news) != combined_snapshot_hash(
        market, news
    )


def test_context_bar_order_does_not_change_the_hash() -> None:
    market, news = _snapshots()
    a = market.model_copy(
        update={
            "context_bars": {
                "SPY": [_bar("SPY", 13), _bar("SPY", 14)],
                "QQQ": [_bar("QQQ", 14)],
            }
        }
    )
    b = market.model_copy(
        update={
            "context_bars": {
                "QQQ": [_bar("QQQ", 14)],
                "SPY": [_bar("SPY", 14), _bar("SPY", 13)],
            }
        }
    )
    assert combined_snapshot_hash(a, news) == combined_snapshot_hash(b, news)


def test_fundamentals_and_macro_change_the_hash() -> None:
    market, news = _snapshots()
    now = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
    base = combined_snapshot_hash(market, news)
    f = combined_snapshot_hash(market, news, fundamentals=_fundamentals(now))
    m = combined_snapshot_hash(market, news, macro=_macro(now))
    assert len({base, f, m}) == 3


def test_retrieved_at_alone_does_not_change_fundamentals_hash() -> None:
    market, news = _snapshots()
    t1 = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)
    assert combined_snapshot_hash(
        market, news, fundamentals=_fundamentals(t1), macro=_macro(t1)
    ) == combined_snapshot_hash(
        market, news, fundamentals=_fundamentals(t2), macro=_macro(t2)
    )


def test_summary_details_and_source_type_change_the_hash() -> None:
    market, news = _snapshots()
    base = combined_snapshot_hash(market, news)
    updates = [
        {"summary": "text"},
        {"details": EvidenceDetails(providers=["sec"])},
        {"source_type": "filing"},
    ]
    seen = {base}
    for update in updates:
        changed = news.model_copy(
            update={"items": [news.items[0].model_copy(update=update), news.items[1]]}
        )
        seen.add(combined_snapshot_hash(market, changed))
    assert len(seen) == 4
