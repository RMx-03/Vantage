from dataclasses import dataclass
from datetime import UTC, date, datetime
import math
from numbers import Real
from typing import Any, cast

from app.domain.errors import VantageError
from app.domain.research import ComponentQuality, DailyBar, MarketSnapshot
from app.services.sessions import XNYS, market_snapshot_hash


@dataclass(frozen=True)
class RawBar:
    """One provider bar before validation; every value may be of any type."""

    session_date: date
    open: object
    high: object
    low: object
    close: object
    adjusted_close: object
    volume: object


def _invalid(message: str) -> VantageError:
    return VantageError(
        code="INVALID_PRICE_SERIES",
        safe_message=message,
        missing_value_count=1,
    )


def _validate_bar(
    raw: RawBar,
    *,
    symbol: str,
    provider: str,
    retrieved_at: datetime,
    adjustment_state: str,
) -> DailyBar:
    raw_prices = (raw.open, raw.high, raw.low, raw.close, raw.adjusted_close)
    raw_volume = raw.volume
    if (
        any(
            not isinstance(value, Real) or isinstance(value, bool)
            for value in raw_prices
        )
        or not isinstance(raw_volume, Real)
        or isinstance(raw_volume, bool)
    ):
        raise _invalid("OHLCV values must be valid and complete.")

    try:
        price_values = tuple(float(cast(Any, value)) for value in raw_prices)
        volume_float = float(raw_volume)
    except (OverflowError, TypeError, ValueError) as e:
        raise _invalid("OHLCV values must be valid and complete.") from e

    if (
        any(not math.isfinite(value) or value <= 0 for value in price_values)
        or not math.isfinite(volume_float)
        or volume_float < 0
        or not volume_float.is_integer()
    ):
        raise _invalid("OHLCV values must be valid and complete.")

    open_val, high_val, low_val, close_val, adj_close_val = price_values
    volume_val = int(cast(Any, raw_volume))
    if high_val < max(open_val, close_val, low_val) or low_val > min(
        open_val, close_val, high_val
    ):
        raise _invalid("OHLC values have invalid price geometry.")

    return DailyBar(
        symbol=symbol,
        session_date=raw.session_date,
        open=open_val,
        high=high_val,
        low=low_val,
        close=close_val,
        adjusted_close=adj_close_val,
        volume=volume_val,
        currency="USD",
        provider=provider,
        retrieved_at=retrieved_at,
        adjustment_state=cast(Any, adjustment_state),
    )


def build_market_snapshot(
    *,
    symbol: str,
    raw_bars: list[RawBar],
    expected_sessions: tuple[date, ...],
    end_session: date,
    provider: str,
    retrieved_at: datetime,
    adjustment_state: str,
) -> MarketSnapshot:
    normalized_symbol = symbol.strip().upper()
    now = retrieved_at.astimezone(UTC)
    session_dates = [raw.session_date for raw in raw_bars]

    if len(session_dates) != len(set(session_dates)):
        raise VantageError(
            code="INVALID_PRICE_SERIES",
            safe_message="Market price series contains duplicate sessions.",
            duplicate_session_count=len(session_dates) - len(set(session_dates)),
        )

    required_sessions = set(expected_sessions)
    actual_sessions = set(session_dates)
    missing_sessions = required_sessions - actual_sessions
    if missing_sessions or actual_sessions - required_sessions:
        raise VantageError(
            code="INVALID_PRICE_SERIES",
            safe_message="Market price series does not contain the required sessions.",
            missing_value_count=len(missing_sessions),
        )

    bars = [
        _validate_bar(
            raw,
            symbol=normalized_symbol,
            provider=provider,
            retrieved_at=now,
            adjustment_state=adjustment_state,
        )
        for raw in raw_bars
    ]
    if not bars:
        raise VantageError(
            code="MARKET_DATA_PROVIDER_FAILED",
            safe_message="No daily bars in requested session range.",
        )

    has_zero_volume = any(bar.volume == 0 for bar in bars)
    bars.sort(key=lambda bar: bar.session_date)
    quality = (
        ComponentQuality.FRESH
        if bars[-1].session_date == end_session
        else ComponentQuality.STALE
    )
    return MarketSnapshot(
        symbol=normalized_symbol,
        bars=bars,
        provider=provider,
        retrieved_at=now,
        as_of=XNYS.session_close(end_session).to_pydatetime().astimezone(UTC),
        latest_completed_session=end_session,
        content_hash=market_snapshot_hash(normalized_symbol, bars),
        quality=quality,
        volume_quality=(
            ComponentQuality.PARTIAL if has_zero_volume else ComponentQuality.FRESH
        ),
    )


def validate_context_bars(
    symbol: str,
    raw_bars: list[RawBar],
    provider: str,
    retrieved_at: datetime,
    adjustment_state: str,
) -> list[DailyBar] | None:
    """Per-bar checks only (no session-set rule); None when any bar is invalid."""
    normalized_symbol = symbol.strip().upper()
    now = retrieved_at.astimezone(UTC)
    try:
        return [
            _validate_bar(
                raw,
                symbol=normalized_symbol,
                provider=provider,
                retrieved_at=now,
                adjustment_state=adjustment_state,
            )
            for raw in raw_bars
        ]
    except VantageError:
        return None
