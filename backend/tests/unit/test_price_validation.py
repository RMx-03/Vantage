from datetime import UTC, date, datetime
import math

import pytest

from app.domain.errors import VantageError
from app.domain.research import ComponentQuality
from app.providers.price_validation import (
    RawBar,
    build_market_snapshot,
    validate_context_bars,
)
from app.services.sessions import XNYS, trailing_xnys_sessions

END = date(2026, 9, 14)
SESSIONS = trailing_xnys_sessions(END)
NOW = datetime(2026, 9, 14, 22, 0, tzinfo=UTC)


def _bar(session: date, **overrides: object) -> RawBar:
    values: dict[str, object] = {
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "adjusted_close": 101.0,
        "volume": 1000,
    }
    values.update(overrides)
    return RawBar(session_date=session, **values)  # type: ignore[arg-type]


def _bars(**overrides: object) -> list[RawBar]:
    return [_bar(session, **overrides) for session in SESSIONS]


def _build(raw_bars: list[RawBar], end: date = END):  # type: ignore[no-untyped-def]
    return build_market_snapshot(
        symbol="aapl",
        raw_bars=raw_bars,
        expected_sessions=SESSIONS,
        end_session=end,
        provider="test",
        retrieved_at=NOW,
        adjustment_state="split_and_dividend_adjusted",
    )


def test_valid_series_builds_a_fresh_snapshot() -> None:
    snapshot = _build(_bars())
    assert snapshot.symbol == "AAPL"
    assert snapshot.quality is ComponentQuality.FRESH
    assert snapshot.volume_quality is ComponentQuality.FRESH
    assert snapshot.latest_completed_session == END
    assert snapshot.as_of == XNYS.session_close(END).to_pydatetime().astimezone(UTC)
    assert len(snapshot.bars) == len(SESSIONS)
    assert snapshot.bars[0].currency == "USD"
    assert snapshot.content_hash


def test_duplicate_session_is_rejected_with_count() -> None:
    raw = _bars() + [_bar(SESSIONS[0])]
    with pytest.raises(VantageError) as exc:
        _build(raw)
    assert exc.value.code == "INVALID_PRICE_SERIES"
    assert exc.value.duplicate_session_count == 1
    assert "duplicate sessions" in exc.value.safe_message


def test_missing_session_is_rejected_with_count() -> None:
    with pytest.raises(VantageError) as exc:
        _build(_bars()[1:])
    assert exc.value.code == "INVALID_PRICE_SERIES"
    assert exc.value.missing_value_count == 1
    assert "required sessions" in exc.value.safe_message


@pytest.mark.parametrize(
    "overrides",
    [
        {"open": "100"},
        {"close": None},
        {"high": True},
        {"low": math.nan},
        {"close": 0.0},
        {"open": -1.0},
        {"volume": -5},
        {"volume": 10.5},
        {"volume": math.inf},
        {"volume": "1000"},
    ],
)
def test_invalid_values_are_rejected(overrides: dict[str, object]) -> None:
    raw = _bars()
    raw[3] = _bar(SESSIONS[3], **overrides)
    with pytest.raises(VantageError) as exc:
        _build(raw)
    assert exc.value.code == "INVALID_PRICE_SERIES"
    assert exc.value.missing_value_count == 1
    assert exc.value.safe_message == "OHLCV values must be valid and complete."


def test_bad_geometry_is_rejected() -> None:
    raw = _bars()
    raw[2] = _bar(SESSIONS[2], high=98.0)
    with pytest.raises(VantageError) as exc:
        _build(raw)
    assert exc.value.code == "INVALID_PRICE_SERIES"
    assert exc.value.missing_value_count == 1
    assert exc.value.safe_message == "OHLC values have invalid price geometry."


def test_zero_volume_marks_volume_partial() -> None:
    raw = _bars()
    raw[4] = _bar(SESSIONS[4], volume=0)
    snapshot = _build(raw)
    assert snapshot.volume_quality is ComponentQuality.PARTIAL
    assert snapshot.quality is ComponentQuality.FRESH


def test_last_bar_before_end_session_is_stale() -> None:
    later_end = date(2026, 9, 15)
    sessions = trailing_xnys_sessions(END)
    snapshot = build_market_snapshot(
        symbol="AAPL",
        raw_bars=[_bar(session) for session in sessions],
        expected_sessions=sessions,
        end_session=later_end,
        provider="test",
        retrieved_at=NOW,
        adjustment_state="split_and_dividend_adjusted",
    )
    assert snapshot.quality is ComponentQuality.STALE
    assert snapshot.latest_completed_session == later_end


def test_validate_context_bars_returns_bars() -> None:
    bars = validate_context_bars(
        "spy", _bars()[:5], "test", NOW, "split_and_dividend_adjusted"
    )
    assert bars is not None
    assert [b.session_date for b in bars] == list(SESSIONS[:5])
    assert bars[0].symbol == "SPY"


def test_validate_context_bars_returns_none_on_one_bad_bar() -> None:
    raw = _bars()[:5]
    raw[1] = _bar(SESSIONS[1], close=0.0)
    assert (
        validate_context_bars("SPY", raw, "test", NOW, "split_and_dividend_adjusted")
        is None
    )


def test_validate_context_bars_has_no_session_set_rule() -> None:
    assert (
        validate_context_bars(
            "SPY", _bars()[3:4], "test", NOW, "split_and_dividend_adjusted"
        )
        is not None
    )
