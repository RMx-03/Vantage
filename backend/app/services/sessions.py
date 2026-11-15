from datetime import UTC, date, datetime
import hashlib
import json

import exchange_calendars

from app.domain.research import DailyBar
from app.services.snapshots import bar_fields

XNYS = exchange_calendars.get_calendar("XNYS")


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


def market_snapshot_hash(symbol: str, bars: list[DailyBar]) -> str:
    sorted_bars = sorted(bars, key=lambda b: b.session_date)
    payload = {
        "symbol": symbol.strip().upper(),
        "bars": [bar_fields(bar) for bar in sorted_bars],
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
