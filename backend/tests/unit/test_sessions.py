import json
from pathlib import Path

from app.domain.research import MarketSnapshot
from app.services.sessions import market_snapshot_hash
from app.services.snapshots import bar_fields

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
# Recorded from yfinance_provider.snapshot_hash before the helpers moved.
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
