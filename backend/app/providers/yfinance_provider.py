from datetime import UTC, date, datetime, timedelta
import hashlib
import logging
from typing import Any

import pandas as pd
import yfinance as yf

from app.domain.errors import VantageError
from app.domain.research import (
    ComponentQuality,
    DailyBar,
    MarketSnapshot,
    NewsItem,
    NewsSnapshot,
)
from app.domain.urls import normalize_url
from app.providers.contracts import MarketDataProvider, NewsProvider
from app.providers.price_validation import RawBar, build_market_snapshot
from app.services.sessions import (
    XNYS,
    latest_completed_xnys_close,
    latest_completed_xnys_session,
    market_snapshot_hash,
    trailing_xnys_sessions,
)

logger = logging.getLogger(__name__)

snapshot_hash = market_snapshot_hash
__all__ = [
    "XNYS",
    "YFinanceSnapshotProvider",
    "latest_completed_xnys_close",
    "latest_completed_xnys_session",
    "snapshot_hash",
    "trailing_xnys_sessions",
]
US_EQUITY_EXCHANGES = frozenset(
    {"ASE", "BATS", "BTS", "IEX", "NCM", "NGM", "NMS", "NYQ", "PCX"}
)


def _search_news(symbol: str, count: int) -> list[dict[str, Any]]:
    return list(yf.Search(symbol, news_count=count).news or [])


class YFinanceSnapshotProvider(MarketDataProvider, NewsProvider):
    name: str = "yfinance"

    def __init__(self, ticker_factory: Any = None, search_factory: Any = None) -> None:
        self._ticker_factory = ticker_factory or yf.Ticker
        self._search_factory = search_factory or _search_news

    def fetch_daily_snapshot(
        self,
        symbol: str,
        start_session: date,
        end_session: date,
        retrieved_at: datetime,
        *,
        context_symbols: tuple[str, ...] = (),
    ) -> MarketSnapshot:
        del (
            context_symbols
        )  # yfinance serves no context series; context_bars stays empty
        normalized_symbol = symbol.strip().upper()
        now = retrieved_at.astimezone(UTC)

        try:
            ticker = self._ticker_factory(normalized_symbol)
        except Exception as e:
            raise VantageError(
                code="MARKET_DATA_PROVIDER_FAILED",
                safe_message="Market data provider was unavailable.",
            ) from e

        try:
            instrument_info = ticker.info
            quote_type = str(instrument_info.get("quoteType", "")).upper()
            exchange = str(instrument_info.get("exchange", "")).upper()
        except Exception as e:
            raise VantageError(
                code="MARKET_DATA_PROVIDER_FAILED",
                safe_message="Market instrument metadata could not be verified.",
            ) from e
        if quote_type != "EQUITY" or exchange not in US_EQUITY_EXCHANGES:
            raise VantageError(
                code="UNSUPPORTED_INSTRUMENT",
                safe_message="The symbol must identify a supported US-listed equity.",
            )

        # Fail closed unless the provider positively identifies USD.
        try:
            fast_info = getattr(ticker, "fast_info", None)
            currency = (
                fast_info.get("currency")
                if isinstance(fast_info, dict)
                else getattr(fast_info, "currency", None)
            )
        except VantageError:
            raise
        except Exception as e:
            raise VantageError(
                code="MARKET_DATA_PROVIDER_FAILED",
                safe_message="Market instrument metadata could not be verified.",
            ) from e
        if not isinstance(currency, str) or currency.strip().upper() != "USD":
            raise VantageError(
                code="UNSUPPORTED_INSTRUMENT",
                safe_message="The symbol must identify a USD-denominated US-listed equity.",
            )

        # End date in yfinance history is exclusive, so add 1 day
        query_start = start_session.isoformat()
        query_end = (end_session + timedelta(days=1)).isoformat()

        try:
            df: pd.DataFrame = ticker.history(
                start=query_start,
                end=query_end,
                auto_adjust=False,
            )
        except Exception as e:
            raise VantageError(
                code="MARKET_DATA_PROVIDER_FAILED",
                safe_message="Market prices could not be retrieved.",
            ) from e

        if df is None or df.empty:
            raise VantageError(
                code="MARKET_DATA_PROVIDER_FAILED",
                safe_message="No market prices were available for the requested symbol.",
            )

        # Normalize only date-like provider indexes; do not coerce malformed labels.
        session_dates: list[date] = []
        for index_value in df.index:
            if isinstance(index_value, datetime):
                session_dates.append(index_value.date())
            elif isinstance(index_value, date):
                session_dates.append(index_value)
            else:
                raise VantageError(
                    code="INVALID_PRICE_SERIES",
                    safe_message="Market price series contains an invalid session index.",
                )

        price_columns = tuple(
            df.get(field) for field in ("Open", "High", "Low", "Close", "Adj Close")
        )
        volume_column = df.get("Volume")

        def _cell(column: Any, position: int) -> object:
            return column.iloc[position] if column is not None else None

        raw_bars = [
            RawBar(
                session_date=session_d,
                open=_cell(price_columns[0], position),
                high=_cell(price_columns[1], position),
                low=_cell(price_columns[2], position),
                close=_cell(price_columns[3], position),
                adjusted_close=_cell(price_columns[4], position),
                volume=_cell(volume_column, position),
            )
            for position, session_d in enumerate(session_dates)
        ]
        return build_market_snapshot(
            symbol=normalized_symbol,
            raw_bars=raw_bars,
            expected_sessions=trailing_xnys_sessions(end_session),
            end_session=end_session,
            provider=self.name,
            retrieved_at=now,
            adjustment_state="split_and_dividend_adjusted",
        )

    def fetch_company_news(
        self,
        symbol: str,
        cutoff: datetime,
        retrieved_at: datetime,
        lookback_days: int,
        limit: int = 10,
    ) -> NewsSnapshot:
        normalized_symbol = symbol.strip().upper()
        cutoff_utc = cutoff.astimezone(UTC)
        retrieved_at_utc = retrieved_at.astimezone(UTC)
        window_start = cutoff_utc - timedelta(days=lookback_days)

        try:
            ticker = self._ticker_factory(normalized_symbol)
            try:
                raw_news = ticker.get_news(count=max(limit * 10, 100))
            except TypeError:
                raw_news = ticker.get_news()
        except Exception as e:
            raise VantageError(
                code="NEWS_PROVIDER_FAILED",
                safe_message="Company news could not be retrieved.",
            ) from e

        source = "quote"
        if not raw_news:
            # Yahoo withdrew the quote-news endpoint on 2026-10-02 (404, which
            # yfinance returns as []). Its search endpoint still serves news,
            # tagged with the tickers each article covers; keep only this
            # symbol's. A failure here is a broken source, not "no news".
            source = "search"
            try:
                searched = self._search_factory(normalized_symbol, max(limit * 5, 50))
            except Exception as e:
                raise VantageError(
                    code="NEWS_PROVIDER_FAILED",
                    safe_message="Company news could not be retrieved.",
                ) from e
            raw_news = [
                raw
                for raw in searched or []
                if isinstance(raw, dict)
                and normalized_symbol
                in {str(t).upper() for t in raw.get("relatedTickers") or []}
            ]

        if not raw_news:
            logger.info(
                "news.fetched symbol=%s source=%s raw=0 kept=0",
                normalized_symbol,
                source,
            )
            return NewsSnapshot(
                symbol=normalized_symbol,
                items=[],
                provider=self.name,
                retrieved_at=retrieved_at_utc,
                quality=ComponentQuality.MISSING,
            )

        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()
        items: list[NewsItem] = []

        # Item construction is part of the provider boundary: a malformed
        # upstream article must degrade into a typed provider failure, not
        # escape as an untyped error the service reports as INTERNAL_ERROR.
        try:
            for raw in raw_news:
                if not isinstance(raw, dict):
                    continue

                raw_id: str | None = None
                title: str | None = None
                publisher: str | None = None
                url: str | None = None
                event_time: datetime | None = None

                if "content" in raw and isinstance(raw["content"], dict):
                    content = raw["content"]
                    raw_id = raw.get("id") or content.get("id")
                    title = content.get("title")
                    prov = content.get("provider")
                    if isinstance(prov, dict):
                        publisher = prov.get("displayName")
                    canonical = content.get("canonicalUrl")
                    if isinstance(canonical, dict):
                        url = canonical.get("url")
                    if not url:
                        click = content.get("clickThroughUrl")
                        if isinstance(click, dict):
                            url = click.get("url")
                    pub_date = content.get("pubDate")
                    if pub_date:
                        try:
                            event_time = datetime.fromisoformat(
                                str(pub_date).replace("Z", "+00:00")
                            )
                        except Exception:
                            event_time = None
                        # fromisoformat accepts a timezone-less value, but an
                        # unanchored instant cannot be placed in the run window.
                        # Assuming a zone would fabricate provenance, so treat it
                        # as missing -- a state the snapshot already models.
                        if event_time is not None and event_time.tzinfo is None:
                            event_time = None
                else:
                    raw_id = raw.get("uuid") or raw.get("id")
                    title = raw.get("title")
                    publisher = raw.get("publisher")
                    url = raw.get("link")
                    pub_time = raw.get("providerPublishTime")
                    if pub_time and isinstance(pub_time, (int, float)):
                        try:
                            event_time = datetime.fromtimestamp(pub_time, tz=UTC)
                        except Exception:
                            event_time = None

                if not title or not str(title).strip():
                    continue

                clean_title = str(title).strip()
                norm_url = normalize_url(url)
                clean_pub = (
                    str(publisher).strip()
                    if publisher and str(publisher).strip()
                    else None
                )

                # Calculate deterministic content hash
                time_str = event_time.isoformat() if event_time else ""
                pub_key = (clean_pub or "").lower()
                norm_hash = hashlib.sha256(
                    f"{pub_key}|{clean_title.lower()}|{time_str}".encode("utf-8")
                ).hexdigest()

                ev_id = (
                    str(raw_id).strip()
                    if raw_id and str(raw_id).strip()
                    else f"news-{norm_hash[:16]}"
                )

                # Deduplication rules:
                # 1. Provider ID
                if ev_id in seen_ids:
                    continue
                # 2. Normalized URL
                if norm_url and norm_url in seen_urls:
                    continue
                # 3. Content hash
                if norm_hash in seen_hashes:
                    continue

                seen_ids.add(ev_id)
                if norm_url:
                    seen_urls.add(norm_url)
                seen_hashes.add(norm_hash)

                items.append(
                    NewsItem(
                        evidence_id=ev_id,
                        provider=self.name,
                        publisher=clean_pub,
                        title=clean_title,
                        # Never fall back to the raw provider value: that would
                        # re-admit exactly the schemes normalization rejected.
                        url=norm_url,
                        event_time=event_time,
                        retrieved_at=retrieved_at_utc,
                        content_hash=norm_hash,
                    )
                )
        except VantageError:
            # Already typed and already safe -- do not relabel it.
            raise
        except Exception as e:
            raise VantageError(
                code="NEWS_PROVIDER_FAILED",
                safe_message="Company news could not be retrieved.",
            ) from e

        # Sort items by event_time descending (None at end)
        eod_items = [
            item
            for item in items
            if item.event_time is None or window_start < item.event_time <= cutoff_utc
        ]
        if eod_items:
            items = eod_items
        else:
            # When weekend/after-hours news floods the provider buffer and leaves no
            # pre-cutoff articles, fall back to recent news up to retrieved_at_utc so
            # live research runs are not left with zero evidence.
            items = [
                item
                for item in items
                if item.event_time is None
                or window_start < item.event_time <= retrieved_at_utc
            ]
        items.sort(
            key=lambda x: (
                x.event_time is not None,
                x.event_time or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )

        capped_items = items[:limit] if limit > 0 else items
        # Counts only: titles and URLs are third-party content, and an empty
        # result must be distinguishable from a dead source in the logs.
        logger.info(
            "news.fetched symbol=%s source=%s raw=%d kept=%d",
            normalized_symbol,
            source,
            len(raw_news),
            len(capped_items),
        )

        if not capped_items:
            quality = ComponentQuality.MISSING
        elif any(
            item.publisher is None or item.event_time is None or item.url is None
            for item in capped_items
        ):
            quality = ComponentQuality.PARTIAL
        else:
            quality = ComponentQuality.FRESH

        valid_times = [i.event_time for i in capped_items if i.event_time is not None]
        coverage_start = min(valid_times) if valid_times else None
        coverage_end = max(valid_times) if valid_times else None

        return NewsSnapshot(
            symbol=normalized_symbol,
            items=capped_items,
            provider=self.name,
            retrieved_at=retrieved_at_utc,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            quality=quality,
        )
