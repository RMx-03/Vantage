from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import Settings
from app.domain.research import ComponentQuality
from app.providers.fixture_provider import FixtureProvider
from app.providers.registry import build_providers
from app.providers.yfinance_provider import (
    latest_completed_xnys_close,
    trailing_xnys_sessions,
)

NOW = datetime(2026, 11, 27, 22, 0, tzinfo=UTC)

PROVIDER_ENV = (
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET_KEY",
    "FINNHUB_API_KEY",
    "FRED_API_KEY",
    "TIINGO_API_KEY",
    "SEC_USER_AGENT",
    "MARKET_PROVIDER",
    "NEWS_PROVIDERS",
    "FILINGS_PROVIDER",
    "MACRO_PROVIDER",
    "PRICE_CROSSCHECK_PROVIDER",
    "PROVIDER_TIMEOUT_SECONDS",
)


def _clean_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)


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


def test_registry_selects_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_provider_env(monkeypatch)
    settings = Settings(
        _env_file=None, MARKET_PROVIDER="fixture", NEWS_PROVIDERS="fixture"
    )
    providers = build_providers(settings)
    assert isinstance(providers.market, FixtureProvider)
    assert len(providers.news) == 1
    assert isinstance(providers.news[0], FixtureProvider)


def test_recorded_market_bars_pass_price_validation() -> None:
    from app.providers.fixture_provider import _load
    from app.providers.price_validation import RawBar, build_market_snapshot

    end = date(2026, 11, 27)
    sessions = trailing_xnys_sessions(end)
    data = _load("market.json")
    for key in ("default", "SPY", "sector"):
        rows = data[key][-len(sessions) :]
        assert len(rows) == len(sessions)
        raw_bars = [
            RawBar(
                session_date=session,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                adjusted_close=row["adjusted_close"],
                volume=row["volume"],
            )
            for session, row in zip(sessions, rows, strict=True)
        ]
        snapshot = build_market_snapshot(
            symbol="AAPL",
            raw_bars=raw_bars,
            expected_sessions=sessions,
            end_session=end,
            provider="fixture",
            retrieved_at=NOW,
            adjustment_state="split_and_dividend_adjusted",
        )
        assert len(snapshot.bars) == len(sessions)


def test_recorded_news_items_build_news_items() -> None:
    from app.domain.research import NewsItem
    from app.providers.fixture_provider import _load

    records = _load("news.json")
    assert records
    for index, rec in enumerate(records):
        item = NewsItem(
            evidence_id=f"fixture-AAPL-{index}",
            provider="fixture",
            publisher=rec["publisher"],
            title=rec["title_template"].format(symbol="AAPL"),
            summary=rec["summary_template"].format(symbol="AAPL"),
            url="https://example.com" + rec["url_path"].format(n="aapl"),
            event_time=NOW - timedelta(hours=rec["offset_hours"]),
            retrieved_at=NOW,
            content_hash="a" * 64,
        )
        assert item.title


def test_news_items_carry_fixture_details() -> None:
    cutoff = latest_completed_xnys_close(NOW)
    snap = FixtureProvider().fetch_company_news("MSFT", cutoff, NOW, 7, 3)
    for item in snap.items:
        assert item.details is not None
        assert item.details.providers == ["fixture"]
        assert item.details.tagged_symbols == ["MSFT"]


def test_filing_evidence_shape_and_placement() -> None:
    cutoff = latest_completed_xnys_close(NOW)
    snap = FixtureProvider().fetch_filing_evidence("msft", cutoff, NOW, 30)

    assert snap.symbol == "MSFT"
    assert snap.provider == "fixture"
    assert snap.quality == ComponentQuality.FRESH
    assert snap.sic_code == "3571"
    assert snap.company_name == "Fixture Company Inc."
    assert snap.cik is not None and len(snap.cik) == 10 and snap.cik.isdigit()
    assert snap.insider_filing_count == 3
    filings = [i for i in snap.items if i.source_type == "filing"]
    insiders = [i for i in snap.items if i.source_type == "insider_transaction"]
    assert len(filings) == 2
    assert len(insiders) == 3
    assert {i.title for i in filings} == {"Form 8-K (Items 2.02, 9.01)", "Form 10-Q"}
    assert all(i.evidence_id.startswith("fixture-") for i in snap.items)
    assert len({i.evidence_id for i in snap.items}) == 5
    assert all(i.url and i.url.startswith("https://example.com/") for i in snap.items)
    assert all(i.details and i.details.providers == ["fixture"] for i in snap.items)
    for item in snap.items:
        assert item.event_time is not None and item.event_time <= cutoff
    assert all(i.event_time >= cutoff - timedelta(days=30) for i in filings)  # type: ignore[operator]
    assert all(i.event_time >= cutoff - timedelta(days=90) for i in insiders)  # type: ignore[operator]
    states = {i.details.parse_state for i in insiders if i.details}
    directions = {i.details.direction for i in insiders if i.details}
    assert states == {"parsed", "unparsed"}
    assert {"acquired", "disposed", None} == directions
    unparsed = [
        i for i in insiders if i.details and i.details.parse_state == "unparsed"
    ]
    assert len(unparsed) == 1
    assert unparsed[0].details is not None
    assert unparsed[0].details.transaction_code is None
    assert unparsed[0].details.direction is None
    assert all(
        "Fixture Officer" in i.title
        for i in insiders
        if i.details and i.details.parse_state == "parsed"
    )
    eight_k = next(i for i in filings if "8-K" in i.title)
    assert eight_k.details is not None
    assert eight_k.details.item_codes == ["2.02", "9.01"]
    assert eight_k.details.form_type == "8-K"


def test_filing_evidence_is_deterministic() -> None:
    cutoff = latest_completed_xnys_close(NOW)
    a = FixtureProvider().fetch_filing_evidence("AAPL", cutoff, NOW, 30)
    b = FixtureProvider().fetch_filing_evidence("AAPL", cutoff, NOW, 30)
    assert a == b


def test_fundamentals_are_fixed_and_fresh() -> None:
    snap = FixtureProvider().fetch_fundamentals("aapl", NOW)
    assert snap.symbol == "AAPL"
    assert snap.provider == "fixture"
    assert snap.quality == ComponentQuality.FRESH
    assert snap.form == "10-K"
    assert snap.revenue_concept == "Revenues"
    assert snap.fiscal_year is not None and snap.period_end is not None
    assert snap.revenue is not None and snap.prior_revenue is not None
    assert snap.net_income is not None


def test_macro_series_dated_end_session() -> None:
    from app.providers.fred import MACRO_SERIES

    end = date(2026, 11, 27)
    snap = FixtureProvider().fetch_macro(end, NOW)
    assert snap.provider == "fixture"
    assert snap.quality == ComponentQuality.FRESH
    assert tuple(o.series_id for o in snap.observations) == MACRO_SERIES
    for obs in snap.observations:
        assert obs.value is not None
        assert obs.observation_date == end
        assert obs.quality == ComponentQuality.FRESH


def test_fixture_sector_etf_has_context_bars() -> None:
    from app.services.sectors import sic_to_sector_etf

    cutoff = latest_completed_xnys_close(NOW)
    snap = FixtureProvider().fetch_filing_evidence("AAPL", cutoff, NOW, 30)
    etf = sic_to_sector_etf(snap.sic_code)
    assert etf is not None
    end = date(2026, 11, 27)
    start = trailing_xnys_sessions(end)[0]
    market = FixtureProvider().fetch_daily_snapshot(
        "AAPL", start, end, NOW, context_symbols=("SPY", etf)
    )
    assert len(market.context_bars[etf]) == len(market.bars)


def test_registry_builds_fixture_for_all_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_provider_env(monkeypatch)
    settings = Settings(
        _env_file=None,
        MARKET_PROVIDER="fixture",
        NEWS_PROVIDERS="fixture",
        FILINGS_PROVIDER="fixture",
        MACRO_PROVIDER="fixture",
    )
    providers = build_providers(settings)
    assert isinstance(providers.filings, FixtureProvider)
    assert isinstance(providers.fundamentals, FixtureProvider)
    assert isinstance(providers.macro, FixtureProvider)
    assert providers.not_configured == ("crosscheck",)
