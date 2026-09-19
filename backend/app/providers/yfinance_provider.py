from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import math
from numbers import Real
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import exchange_calendars
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
from app.providers.contracts import MarketDataProvider, NewsProvider

XNYS = exchange_calendars.get_calendar("XNYS")
US_EQUITY_EXCHANGES = frozenset(
    {"ASE", "BATS", "BTS", "IEX", "NCM", "NGM", "NMS", "NYQ", "PCX"}
)


def latest_completed_xnys_close(now: datetime) -> datetime:
    now_utc = now.astimezone(UTC)
    candidate = XNYS.date_to_session(now_utc.date(), direction="previous")
    close = XNYS.session_close(candidate).to_pydatetime()
    if close > now_utc:
        candidate = XNYS.previous_session(candidate)
        close = XNYS.session_close(candidate).to_pydatetime()
    return close.astimezone(UTC)


def latest_completed_xnys_session(now: datetime) -> date:
    return latest_completed_xnys_close(now).date()


def trailing_xnys_sessions(end_session: date, count: int = 21) -> tuple[date, ...]:
    if count < 1:
        raise ValueError("count must be positive")
    end = XNYS.date_to_session(end_session, direction="previous")
    sessions = XNYS.sessions_window(end, -count)
    return tuple(session.date() for session in sessions)


# A normalized URL is rendered as an href by clients, so only web schemes may
# survive. A provider payload carrying javascript:, data:, or a scheme-relative
# reference is dropped rather than passed through as a link target.
ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def normalize_url(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.netloc:
            return None
        clean_netloc = parsed.netloc.lower()
        clean_scheme = parsed.scheme.lower()
        clean_path = parsed.path.rstrip("/")
        # Filter out tracking query params like utm_*
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if not k.lower().startswith("utm_")
        ]
        clean_query = urlencode(sorted(query_pairs))
        return urlunparse((clean_scheme, clean_netloc, clean_path, "", clean_query, ""))
    except Exception:
        return None


def snapshot_hash(symbol: str, bars: list[DailyBar]) -> str:
    sorted_bars = sorted(bars, key=lambda b: b.session_date)
    canonical_bars = [
        {
            "session_date": bar.session_date.isoformat(),
            "open": round(bar.open, 6),
            "high": round(bar.high, 6),
            "low": round(bar.low, 6),
            "close": round(bar.close, 6),
            "adjusted_close": round(bar.adjusted_close, 6),
            "volume": bar.volume,
            "currency": bar.currency,
            "adjustment_state": bar.adjustment_state,
        }
        for bar in sorted_bars
    ]
    payload = {
        "symbol": symbol.strip().upper(),
        "bars": canonical_bars,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class YFinanceSnapshotProvider(MarketDataProvider, NewsProvider):
    name: str = "yfinance"

    def __init__(self, ticker_factory: Any = None) -> None:
        self._ticker_factory = ticker_factory or yf.Ticker

    def fetch_daily_snapshot(
        self,
        symbol: str,
        start_session: date,
        end_session: date,
        retrieved_at: datetime,
    ) -> MarketSnapshot:
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

        # Verify duplicate session dates
        if len(session_dates) != len(set(session_dates)):
            raise VantageError(
                code="INVALID_PRICE_SERIES",
                safe_message="Market price series contains duplicate sessions.",
                duplicate_session_count=len(session_dates) - len(set(session_dates)),
            )

        required_sessions = set(trailing_xnys_sessions(end_session))
        actual_sessions = set(session_dates)
        missing_sessions = required_sessions - actual_sessions
        if missing_sessions or actual_sessions - required_sessions:
            raise VantageError(
                code="INVALID_PRICE_SERIES",
                safe_message="Market price series does not contain the required sessions.",
                missing_value_count=len(missing_sessions),
            )

        bars: list[DailyBar] = []
        has_zero_volume = False
        price_columns = tuple(
            df.get(field) for field in ("Open", "High", "Low", "Close", "Adj Close")
        )
        volume_column = df.get("Volume")
        for position, session_d in enumerate(session_dates):
            raw_prices = tuple(
                column.iloc[position] if column is not None else None
                for column in price_columns
            )
            raw_volume = (
                volume_column.iloc[position] if volume_column is not None else None
            )
            if (
                any(
                    not isinstance(value, Real) or isinstance(value, bool)
                    for value in raw_prices
                )
                or not isinstance(raw_volume, Real)
                or isinstance(raw_volume, bool)
            ):
                raise VantageError(
                    code="INVALID_PRICE_SERIES",
                    safe_message="OHLCV values must be valid and complete.",
                    missing_value_count=1,
                )

            try:
                price_values = tuple(float(cast(Any, value)) for value in raw_prices)
                volume_float = float(raw_volume)
            except (OverflowError, TypeError, ValueError) as e:
                raise VantageError(
                    code="INVALID_PRICE_SERIES",
                    safe_message="OHLCV values must be valid and complete.",
                    missing_value_count=1,
                ) from e

            if (
                any(not math.isfinite(value) or value <= 0 for value in price_values)
                or not math.isfinite(volume_float)
                or volume_float < 0
                or not volume_float.is_integer()
            ):
                raise VantageError(
                    code="INVALID_PRICE_SERIES",
                    safe_message="OHLCV values must be valid and complete.",
                    missing_value_count=1,
                )

            open_val, high_val, low_val, close_val, adj_close_val = price_values
            volume_val = int(cast(Any, raw_volume))
            if high_val < max(open_val, close_val, low_val) or low_val > min(
                open_val, close_val, high_val
            ):
                raise VantageError(
                    code="INVALID_PRICE_SERIES",
                    safe_message="OHLC values have invalid price geometry.",
                    missing_value_count=1,
                )
            has_zero_volume = has_zero_volume or volume_val == 0

            bars.append(
                DailyBar(
                    symbol=normalized_symbol,
                    session_date=session_d,
                    open=open_val,
                    high=high_val,
                    low=low_val,
                    close=close_val,
                    adjusted_close=adj_close_val,
                    volume=volume_val,
                    currency="USD",
                    provider=self.name,
                    retrieved_at=now,
                    adjustment_state="split_and_dividend_adjusted",
                )
            )

        if not bars:
            raise VantageError(
                code="MARKET_DATA_PROVIDER_FAILED",
                safe_message="No daily bars in requested session range.",
            )

        bars.sort(key=lambda bar: bar.session_date)
        c_hash = snapshot_hash(normalized_symbol, bars)
        latest_bar_session = bars[-1].session_date
        as_of = XNYS.session_close(end_session).to_pydatetime().astimezone(UTC)
        latest_completed = end_session

        quality = (
            ComponentQuality.FRESH
            if latest_bar_session == latest_completed
            else ComponentQuality.STALE
        )

        return MarketSnapshot(
            symbol=normalized_symbol,
            bars=bars,
            provider=self.name,
            retrieved_at=now,
            as_of=as_of,
            latest_completed_session=latest_completed,
            content_hash=c_hash,
            quality=quality,
            volume_quality=(
                ComponentQuality.PARTIAL if has_zero_volume else ComponentQuality.FRESH
            ),
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
            raw_news = ticker.get_news()
        except Exception as e:
            raise VantageError(
                code="NEWS_PROVIDER_FAILED",
                safe_message="Company news could not be retrieved.",
            ) from e

        if not raw_news:
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
                str(publisher).strip() if publisher and str(publisher).strip() else None
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

        # Sort items by event_time descending (None at end)
        items = [
            item
            for item in items
            if item.event_time is None or window_start < item.event_time <= cutoff_utc
        ]
        items.sort(
            key=lambda x: (
                x.event_time is not None,
                x.event_time or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )

        capped_items = items[:limit] if limit > 0 else items

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
