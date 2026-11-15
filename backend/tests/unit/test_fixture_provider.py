from datetime import UTC, date, datetime, timedelta

from app.core.config import Settings
from app.domain.research import ComponentQuality
from app.providers.fixture_provider import FixtureProvider
from app.providers.registry import build_providers
from app.providers.yfinance_provider import (
    latest_completed_xnys_close,
    trailing_xnys_sessions,
)

NOW = datetime(2026, 11, 27, 22, 0, tzinfo=UTC)


def test_bars_land_on_xnys_sessions() -> None:
    end = date(2026, 11, 27)
    sessions = trailing_xnys_sessions(end)
    snap = FixtureProvider().fetch_daily_snapshot("AAPL", sessions[0], end, NOW)

    dates = [bar.session_date for bar in snap.bars]
    assert dates == list(sessions)
    assert date(2026, 11, 26) not in dates
    assert snap.quality == ComponentQuality.FRESH
    assert snap.provider == "fixture"
    assert all(b.adjustment_state == "split_and_dividend_adjusted" for b in snap.bars)

    weekend = datetime(2026, 11, 29, 15, 0, tzinfo=UTC)
    last = latest_completed_xnys_close(weekend).date()
    assert last == date(2026, 11, 27)
    window = trailing_xnys_sessions(last)
    snap = FixtureProvider().fetch_daily_snapshot("AAPL", window[0], last, weekend)
    assert snap.bars[-1].session_date == date(2026, 11, 27)
    assert snap.latest_completed_session == date(2026, 11, 27)


def test_snapshot_is_deterministic() -> None:
    end = date(2026, 11, 27)
    start = trailing_xnys_sessions(end)[0]
    a = FixtureProvider().fetch_daily_snapshot("AAPL", start, end, NOW)
    b = FixtureProvider().fetch_daily_snapshot("AAPL", start, end, NOW)
    assert a.content_hash == b.content_hash


def test_context_symbols_return_bars() -> None:
    end = date(2026, 11, 27)
    start = trailing_xnys_sessions(end)[0]
    snap = FixtureProvider().fetch_daily_snapshot(
        "AAPL", start, end, NOW, context_symbols=("SPY", "XLK")
    )
    assert set(snap.context_bars) == {"SPY", "XLK"}
    for symbol, bars in snap.context_bars.items():
        assert len(bars) == len(snap.bars)
        assert {b.symbol for b in bars} == {symbol}
        assert [b.session_date for b in bars] == [b.session_date for b in snap.bars]


def test_news_respects_window_limit_and_symbol() -> None:
    cutoff = latest_completed_xnys_close(NOW)
    snap = FixtureProvider().fetch_company_news("MSFT", cutoff, NOW, 7, 3)

    assert len(snap.items) == 3
    assert snap.quality == ComponentQuality.FRESH
    times = [i.event_time for i in snap.items]
    assert all(t is not None and t <= cutoff for t in times)
    assert times == sorted(times, reverse=True)  # type: ignore[type-var]
    for index, item in enumerate(snap.items):
        assert "MSFT" in item.title
        assert item.summary is not None and "MSFT" in item.summary
        assert item.url is not None and item.url.startswith("https://example.com")
        assert item.content_hash
        assert item.evidence_id.startswith("fixture-MSFT-")
    assert len({i.evidence_id for i in snap.items}) == 3


def test_news_outside_window_is_missing() -> None:
    cutoff = latest_completed_xnys_close(NOW)
    snap = FixtureProvider().fetch_company_news(
        "MSFT", cutoff - timedelta(days=0), NOW, 0, 10
    )
    assert snap.items == []
    assert snap.quality == ComponentQuality.MISSING


def test_registry_selects_fixture() -> None:
    settings = Settings(MARKET_PROVIDER="fixture", NEWS_PROVIDERS="fixture")
    providers = build_providers(settings)
    assert isinstance(providers.market, FixtureProvider)
    assert len(providers.news) == 1
    assert isinstance(providers.news[0], FixtureProvider)
