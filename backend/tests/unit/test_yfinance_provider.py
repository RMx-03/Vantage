from datetime import UTC, date, datetime
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import app.providers.yfinance_provider as yfinance_provider
import pandas as pd
import pytest

from app.domain.errors import VantageError
from app.domain.research import ComponentQuality, DailyBar
from app.providers.yfinance_provider import (
    YFinanceSnapshotProvider,
    latest_completed_xnys_session,
    normalize_url,
    snapshot_hash,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
START = date(2026, 8, 13)
END = date(2026, 9, 11)
NOW = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 9, 14, 21, 0, tzinfo=UTC)


@pytest.fixture
def history_df() -> pd.DataFrame:
    with open(FIXTURES_DIR / "yfinance_history.json", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df.index = pd.to_datetime(df["Date"])
    df.drop(columns=["Date"], inplace=True)
    first_bar = pd.DataFrame(
        [
            {
                "Open": 149.0,
                "High": 151.0,
                "Low": 148.0,
                "Close": 150.0,
                "Adj Close": 150.0,
                "Volume": 950000,
            }
        ],
        index=pd.to_datetime(["2026-08-13 00:00:00-04:00"]),
    )
    return pd.concat([first_bar, df])


@pytest.fixture
def news_raw() -> list[dict]:
    with open(FIXTURES_DIR / "yfinance_news.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_ticker(history_df: pd.DataFrame, news_raw: list[dict]):
    ticker = MagicMock()
    ticker.history.return_value = history_df
    ticker.get_news.return_value = news_raw
    ticker.fast_info = {"currency": "USD"}
    ticker.info = {"quoteType": "EQUITY", "exchange": "NMS"}
    return ticker


@pytest.fixture
def provider(mock_ticker: MagicMock) -> YFinanceSnapshotProvider:
    return YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)


def test_provider_fetches_history_and_news_once(
    mock_ticker: MagicMock, provider: YFinanceSnapshotProvider, fixed_now: datetime
) -> None:
    market = provider.fetch_daily_snapshot("AAPL", START, END, fixed_now)
    news = provider.fetch_company_news("AAPL", fixed_now, fixed_now, 7, 10)
    assert mock_ticker.history.call_count == 1
    assert mock_ticker.get_news.call_count == 1
    assert market.as_of.date() == date(2026, 9, 11)
    assert market.retrieved_at == fixed_now
    assert all(bar.retrieved_at == fixed_now for bar in market.bars)
    assert all(
        bar.adjustment_state == "split_and_dividend_adjusted" for bar in market.bars
    )
    assert len(news.items) == len({item.evidence_id for item in news.items})


def test_provider_normalizes_price_bars_to_session_order(
    mock_ticker: MagicMock, history_df: pd.DataFrame, fixed_now: datetime
) -> None:
    mock_ticker.history.return_value = history_df.sort_index(ascending=False)
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    market = provider.fetch_daily_snapshot("AAPL", START, END, fixed_now)

    sessions = [bar.session_date for bar in market.bars]
    assert sessions == sorted(sessions)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 14, 19, 59, tzinfo=UTC), date(2026, 9, 11)),
        (datetime(2026, 9, 14, 21, 0, tzinfo=UTC), date(2026, 9, 14)),
        (datetime(2026, 9, 7, 21, 0, tzinfo=UTC), date(2026, 9, 4)),
    ],
)
def test_latest_completed_session_handles_open_market_and_holiday(
    now: datetime, expected: date
) -> None:
    assert latest_completed_xnys_session(now) == expected


def test_black_friday_uses_early_close() -> None:
    now = datetime(2025, 11, 28, 19, 0, tzinfo=UTC)

    assert yfinance_provider.latest_completed_xnys_close(now) == datetime(
        2025, 11, 28, 18, 0, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (
            datetime(2025, 1, 8, 21, 0, tzinfo=UTC),
            datetime(2025, 1, 8, 21, 0, tzinfo=UTC),
        ),
        (
            datetime(2025, 7, 8, 20, 0, tzinfo=UTC),
            datetime(2025, 7, 8, 20, 0, tzinfo=UTC),
        ),
    ],
)
def test_regular_close_respects_dst_and_includes_exact_close(
    now: datetime, expected: datetime
) -> None:
    assert yfinance_provider.latest_completed_xnys_close(now) == expected


def test_exact_trailing_sessions() -> None:
    sessions = yfinance_provider.trailing_xnys_sessions(date(2025, 7, 8), 21)

    assert len(sessions) == 21
    assert sessions[0] == date(2025, 6, 6)
    assert sessions[-1] == date(2025, 7, 8)


def test_news_handles_both_legacy_and_content_schemas(
    provider: YFinanceSnapshotProvider, fixed_now: datetime
) -> None:
    news = provider.fetch_company_news("AAPL", fixed_now, fixed_now, 7, 10)
    # Legacy story
    legacy = next(
        item
        for item in news.items
        if item.evidence_id == "43924729-1b5c-3f92-959c-851532152865"
    )
    assert legacy.publisher == "Reuters"
    assert "apple-stock-rises" in (legacy.url or "")
    # New format story
    new_fmt = next(
        item for item in news.items if item.evidence_id == "new-format-item-01"
    )
    assert new_fmt.publisher == "Wall Street Journal"
    assert new_fmt.title == "Tech Sector Leads Rally"


def test_news_deduplication_by_id_and_normalized_url(
    provider: YFinanceSnapshotProvider, fixed_now: datetime
) -> None:
    news = provider.fetch_company_news("AAPL", fixed_now, fixed_now, 7, 10)
    # The fixture has:
    # 1. 43924729-1b5c-3f92-959c-851532152865 (first occurrence accepted)
    # 2. Duplicate ID 43924729-1b5c-3f92-959c-851532152865 (skipped by provider ID)
    # 3. 99999999-1b5c-3f92-959c-851532152866 with same normalized URL as item 1 (skipped by URL)
    evidence_ids = [item.evidence_id for item in news.items]
    assert "99999999-1b5c-3f92-959c-851532152866" not in evidence_ids
    assert len(evidence_ids) == len(set(evidence_ids))


def test_news_missing_publisher_and_time_retained(
    provider: YFinanceSnapshotProvider, fixed_now: datetime
) -> None:
    news = provider.fetch_company_news("AAPL", fixed_now, fixed_now, 7, 10)
    item = next(
        item for item in news.items if item.evidence_id == "missing-publisher-01"
    )
    assert item.publisher is None
    assert item.event_time is None
    assert item.title == "Unattributed Apple Filing"


def test_empty_prices_raises_vantage_error(mock_ticker: MagicMock) -> None:
    mock_ticker.history.return_value = pd.DataFrame()
    p = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)
    with pytest.raises(VantageError) as exc_info:
        p.fetch_daily_snapshot(
            "AAPL",
            date(2026, 8, 14),
            date(2026, 9, 11),
            datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
        )
    assert exc_info.value.code == "MARKET_DATA_PROVIDER_FAILED"


def test_provider_history_exception_raises_market_failed(
    mock_ticker: MagicMock,
) -> None:
    mock_ticker.history.side_effect = RuntimeError("Connection timeout")
    p = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)
    with pytest.raises(VantageError) as exc_info:
        p.fetch_daily_snapshot(
            "AAPL",
            date(2026, 8, 14),
            date(2026, 9, 11),
            datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
        )
    assert exc_info.value.code == "MARKET_DATA_PROVIDER_FAILED"


def test_provider_news_exception_raises_news_failed(
    mock_ticker: MagicMock, fixed_now: datetime
) -> None:
    mock_ticker.get_news.side_effect = RuntimeError("Yahoo API down")
    p = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)
    with pytest.raises(VantageError) as exc_info:
        p.fetch_company_news("AAPL", fixed_now, fixed_now, 7, 10)
    assert exc_info.value.code == "NEWS_PROVIDER_FAILED"


def test_wrong_currency_raises_market_failed(mock_ticker: MagicMock) -> None:
    mock_ticker.fast_info = {"currency": "EUR"}
    p = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)
    with pytest.raises(VantageError) as exc_info:
        p.fetch_daily_snapshot(
            "AAPL",
            date(2026, 8, 14),
            date(2026, 9, 11),
            datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
        )
    assert exc_info.value.code == "UNSUPPORTED_INSTRUMENT"


def test_missing_currency_is_unsupported(mock_ticker: MagicMock) -> None:
    mock_ticker.fast_info = {}
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert exc_info.value.code == "UNSUPPORTED_INSTRUMENT"


def test_currency_accessor_failure_is_market_provider_failure(
    mock_ticker: MagicMock,
) -> None:
    class RaisingCurrency:
        @property
        def currency(self) -> str:
            raise RuntimeError("currency metadata unavailable")

    mock_ticker.fast_info = RaisingCurrency()
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert exc_info.value.code == "MARKET_DATA_PROVIDER_FAILED"


def test_non_date_history_index_is_rejected(mock_ticker: MagicMock) -> None:
    mock_ticker.history.return_value = mock_ticker.history.return_value.reset_index(
        drop=True
    )
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert exc_info.value.code == "INVALID_PRICE_SERIES"


def test_extreme_real_ohlcv_value_is_rejected(mock_ticker: MagicMock) -> None:
    frame = mock_ticker.history.return_value.copy()
    frame["Open"] = frame["Open"].astype(object)
    frame.loc[frame.index[-1], "Open"] = 10**1000
    mock_ticker.history.return_value = frame
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert exc_info.value.code == "INVALID_PRICE_SERIES"
    assert exc_info.value.missing_value_count == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [("Open", "bad"), ("Volume", None), ("High", float("nan"))],
)
def test_invalid_ohlcv_is_rejected(
    mock_ticker: MagicMock, field: str, value: object
) -> None:
    frame = mock_ticker.history.return_value.copy()
    frame[field] = frame[field].astype(object)
    frame.loc[frame.index[-1], field] = value
    mock_ticker.history.return_value = frame
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert exc_info.value.code == "INVALID_PRICE_SERIES"
    assert exc_info.value.missing_value_count == 1


@pytest.mark.parametrize("volume", [-1, 1.5])
def test_nonintegral_or_negative_volume_is_rejected(
    mock_ticker: MagicMock, volume: float
) -> None:
    frame = mock_ticker.history.return_value.copy()
    frame["Volume"] = frame["Volume"].astype(float)
    frame.loc[frame.index[-1], "Volume"] = volume
    mock_ticker.history.return_value = frame
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert exc_info.value.code == "INVALID_PRICE_SERIES"
    assert exc_info.value.missing_value_count == 1


def test_zero_integral_volume_is_partial(mock_ticker: MagicMock) -> None:
    mock_ticker.history.return_value.loc[
        mock_ticker.history.return_value.index[-1], "Volume"
    ] = 0
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    snapshot = provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert snapshot.volume_quality == ComponentQuality.PARTIAL


@pytest.mark.parametrize(
    ("field", "value"),
    [("High", 168.0), ("Low", 171.0)],
)
def test_invalid_ohlc_geometry_is_rejected(
    mock_ticker: MagicMock, field: str, value: float
) -> None:
    mock_ticker.history.return_value.loc[
        mock_ticker.history.return_value.index[-1], field
    ] = value
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert exc_info.value.code == "INVALID_PRICE_SERIES"


def test_missing_required_session_is_rejected(mock_ticker: MagicMock) -> None:
    mock_ticker.history.return_value = mock_ticker.history.return_value.iloc[1:]
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", START, END, NOW)

    assert exc_info.value.code == "INVALID_PRICE_SERIES"
    assert exc_info.value.missing_value_count == 1


def test_unexpected_session_is_rejected(mock_ticker: MagicMock) -> None:
    unexpected = mock_ticker.history.return_value.iloc[[0]].copy()
    unexpected.index = pd.to_datetime(["2026-08-12 00:00:00-04:00"])
    mock_ticker.history.return_value = pd.concat(
        [unexpected, mock_ticker.history.return_value]
    )
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)

    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot("AAPL", date(2026, 8, 12), END, NOW)

    assert exc_info.value.code == "INVALID_PRICE_SERIES"


@pytest.mark.parametrize(
    "info",
    [
        {"quoteType": "ETF", "exchange": "NMS"},
        {"quoteType": "EQUITY", "exchange": "LSE"},
    ],
)
def test_rejects_non_us_equity_instruments(
    mock_ticker: MagicMock, fixed_now: datetime, info: dict[str, str]
) -> None:
    mock_ticker.info = info
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)
    with pytest.raises(VantageError) as exc_info:
        provider.fetch_daily_snapshot(
            "AAPL", date(2026, 8, 14), date(2026, 9, 11), fixed_now
        )
    assert exc_info.value.code == "UNSUPPORTED_INSTRUMENT"
    assert "LSE" not in exc_info.value.safe_message


def test_news_filters_to_open_closed_lookback_window_and_retains_undated(
    mock_ticker: MagicMock, fixed_now: datetime
) -> None:
    mock_ticker.get_news.return_value = [
        {
            "uuid": "future-news",
            "title": "Future item",
            "publisher": "Reuters",
            "providerPublishTime": int(fixed_now.timestamp()) + 60,
        },
        {
            "uuid": "current-news",
            "title": "Current item",
            "publisher": "Reuters",
            "providerPublishTime": int(fixed_now.timestamp()),
            "link": "https://example.com/current-news",
        },
        {
            "uuid": "inside-news",
            "title": "Inside item",
            "publisher": "Reuters",
            "providerPublishTime": int(fixed_now.timestamp()) - (7 * 24 * 60 * 60) + 1,
            "link": "https://example.com/inside-news",
        },
        {
            "uuid": "boundary-news",
            "title": "Boundary item",
            "publisher": "Reuters",
            "providerPublishTime": int(fixed_now.timestamp()) - (7 * 24 * 60 * 60),
            "link": "https://example.com/boundary-news",
        },
        {
            "uuid": "undated-news",
            "title": "Undated item",
            "publisher": "Reuters",
            "providerPublishTime": None,
            "link": "https://example.com/undated-news",
        },
    ]
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)
    retrieved_at = datetime(2026, 9, 16, 9, 30, tzinfo=UTC)
    result = provider.fetch_company_news("AAPL", fixed_now, retrieved_at, 7, 10)
    assert [item.evidence_id for item in result.items] == [
        "current-news",
        "inside-news",
        "undated-news",
    ]
    assert result.retrieved_at == retrieved_at
    assert all(item.retrieved_at == retrieved_at for item in result.items)
    assert result.quality == ComponentQuality.PARTIAL


def test_duplicate_session_date_raises_error(
    mock_ticker: MagicMock, history_df: pd.DataFrame
) -> None:
    # Duplicate first row
    duplicated_df = pd.concat([history_df.iloc[[0]], history_df])
    mock_ticker.history.return_value = duplicated_df
    p = YFinanceSnapshotProvider(ticker_factory=lambda _: mock_ticker)
    with pytest.raises(VantageError) as exc_info:
        p.fetch_daily_snapshot(
            "AAPL",
            date(2026, 8, 14),
            date(2026, 9, 11),
            datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
        )
    assert exc_info.value.code == "INVALID_PRICE_SERIES"
    assert exc_info.value.duplicate_session_count == 1


def test_snapshot_hash_reproducible_under_reordered_input(fixed_now: datetime) -> None:
    bar1 = DailyBar(
        symbol="AAPL",
        session_date=date(2026, 9, 10),
        open=100.0,
        high=105.0,
        low=99.0,
        close=102.0,
        adjusted_close=102.0,
        volume=1_000_000,
        currency="USD",
        provider="yfinance",
        retrieved_at=fixed_now,
        adjustment_state="split_adjusted",
    )
    bar2 = DailyBar(
        symbol="AAPL",
        session_date=date(2026, 9, 11),
        open=102.0,
        high=106.0,
        low=101.0,
        close=105.0,
        adjusted_close=105.0,
        volume=1_200_000,
        currency="USD",
        provider="yfinance",
        retrieved_at=fixed_now,
        adjustment_state="split_adjusted",
    )
    hash_asc = snapshot_hash("AAPL", [bar1, bar2])
    hash_desc = snapshot_hash("AAPL", [bar2, bar1])
    assert hash_asc == hash_desc
    assert len(hash_asc) == 64


def test_normalize_url_removes_utm_and_fragments() -> None:
    url1 = (
        "https://example.com/news/article-1?utm_source=twitter&utm_medium=social#header"
    )
    url2 = "https://example.com/news/article-1/"
    assert normalize_url(url1) == "https://example.com/news/article-1"
    assert normalize_url(url2) == "https://example.com/news/article-1"


@pytest.mark.parametrize(
    "hostile",
    [
        "javascript:alert(1)",
        "JavaScript:alert(document.cookie)",
        "  javascript:alert(1)  ",
        "java	script:alert(1)",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "//example.com/news/article-1",
        "example.com/news/article-1",
    ],
)
def test_normalize_url_drops_non_http_schemes(hostile: str) -> None:
    """A provider payload must never become a non-http(s) href in the UI."""
    assert normalize_url(hostile) is None


def test_provider_news_item_drops_hostile_url(fixed_now: datetime) -> None:
    ticker = MagicMock()
    ticker.get_news.return_value = [
        {
            "id": "news-1",
            "title": "Apple quarterly progress",
            "publisher": "Reuters",
            "link": "javascript:alert(1)",
            "providerPublishTime": int(fixed_now.timestamp()),
        }
    ]
    provider = YFinanceSnapshotProvider(ticker_factory=lambda _: ticker)
    snapshot = provider.fetch_company_news("AAPL", fixed_now, fixed_now, 7, 10)
    assert [item.url for item in snapshot.items] == [None]
