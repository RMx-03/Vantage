import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.domain.research import DailyBar, MarketSnapshot
from app.services.sessions import (
    latest_completed_xnys_close,
    latest_completed_xnys_session,
    market_snapshot_hash,
    trailing_xnys_sessions,
)
from app.services.snapshots import bar_fields

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
# Recorded from the original market snapshot hash before the helpers moved.
PINNED_FIXTURE_HASH = "9566d4bede3eeb52bc63f9966be6442fada3a1403392354936b59f470580c169"


def _fixture() -> MarketSnapshot:
    data = json.loads((FIXTURES_DIR / "market_snapshot_valid.json").read_text())
    return MarketSnapshot.model_validate(data)


def test_market_snapshot_hash_matches_the_pre_move_value() -> None:
    market = _fixture()
    assert market_snapshot_hash(market.symbol, market.bars) == PINNED_FIXTURE_HASH


def test_market_snapshot_hash_is_order_independent() -> None:
    market = _fixture()
    assert (
        market_snapshot_hash(market.symbol, list(reversed(market.bars)))
        == PINNED_FIXTURE_HASH
    )


def test_bar_fields_lists_exactly_the_hashed_fields() -> None:
    bar = _fixture().bars[0]
    assert set(bar_fields(bar)) == {
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "currency",
        "adjustment_state",
    }


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

    assert latest_completed_xnys_close(now) == datetime(2025, 11, 28, 18, 0, tzinfo=UTC)


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
    assert latest_completed_xnys_close(now) == expected


def test_exact_trailing_sessions() -> None:
    sessions = trailing_xnys_sessions(date(2025, 7, 8), 21)

    assert len(sessions) == 21
    assert sessions[0] == date(2025, 6, 6)
    assert sessions[-1] == date(2025, 7, 8)


def test_snapshot_hash_preserves_exact_accepted_price_values() -> None:
    common = {
        "symbol": "AAPL",
        "session_date": date(2026, 9, 11),
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 1_000_000,
        "currency": "USD",
        "provider": "alpaca",
        "retrieved_at": datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
        "adjustment_state": "split_adjusted",
    }
    first = DailyBar(adjusted_close=102.0000001, **common)
    second = DailyBar(adjusted_close=102.0000002, **common)

    assert market_snapshot_hash("AAPL", [first]) != market_snapshot_hash(
        "AAPL", [second]
    )
