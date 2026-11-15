from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.research import (
    ComponentQuality,
    CrossCheckClose,
    DataQuality,
    EvidenceDetails,
    EvidenceSource,
    FilingsSnapshot,
    FundamentalsSnapshot,
    MacroObservation,
    MacroSnapshot,
    NewsItem,
    PriceCrossCheckSnapshot,
    ProviderRecord,
    RoleQuality,
    SnapshotProvenance,
)

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
NAIVE = datetime(2026, 11, 15, 12, 0)
HASH = "a" * 64


def _item() -> dict:
    return {
        "evidence_id": "e1",
        "provider": "yfinance",
        "title": "Headline",
        "retrieved_at": NOW,
    }


def test_v2_payloads_still_validate() -> None:
    news = NewsItem.model_validate(_item())
    assert news.source_type == "news"
    assert news.summary is None
    assert news.details is None
    source = EvidenceSource.model_validate({**_item(), "source_type": "news"})
    assert source.details is None

    quality = DataQuality.model_validate(
        {
            "overall": "sufficient",
            "prices": "fresh",
            "news": "fresh",
            "model": "healthy",
        }
    )
    assert quality.filings is None
    assert quality.fundamentals is None
    assert quality.macro is None
    assert quality.crosscheck is None

    prov = SnapshotProvenance.model_validate(
        {
            "snapshot_id": uuid4(),
            "content_hash": HASH,
            "market_provider": "yfinance",
            "market_content_hash": HASH,
            "market_as_of": NOW,
            "market_retrieved_at": NOW,
            "window_start": NOW,
            "window_end": NOW,
            "news_provider": "yfinance",
            "news_retrieved_at": NOW,
            "news_quality": "fresh",
        }
    )
    assert prov.providers is None


def test_source_type_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        NewsItem.model_validate({**_item(), "source_type": "press_release"})


def test_evidence_details_forbid_extra() -> None:
    with pytest.raises(ValidationError):
        EvidenceDetails.model_validate({"unknown": 1})
    details = EvidenceDetails()
    assert details.providers == []
    assert details.item_codes == []


def test_role_quality_has_not_configured() -> None:
    assert RoleQuality("not_configured") is RoleQuality.NOT_CONFIGURED
    record = ProviderRecord(
        role="macro", provider=None, retrieved_at=None, quality="not_configured"
    )
    assert record.quality is RoleQuality.NOT_CONFIGURED
    assert record.content_hash is None


def test_new_snapshots_reject_naive_timestamps_and_non_finite_values() -> None:
    q = ComponentQuality.FRESH
    with pytest.raises(ValidationError):
        FilingsSnapshot(
            symbol="AAPL", items=[], provider="sec", retrieved_at=NAIVE, quality=q
        )
    with pytest.raises(ValidationError):
        FundamentalsSnapshot(
            symbol="AAPL", provider="sec", retrieved_at=NAIVE, quality=q
        )
    with pytest.raises(ValidationError):
        MacroSnapshot(provider="fred", retrieved_at=NAIVE, quality=q)
    with pytest.raises(ValidationError):
        PriceCrossCheckSnapshot(
            symbol="AAPL", provider="tiingo", retrieved_at=NAIVE, quality=q
        )
    with pytest.raises(ValidationError):
        ProviderRecord(role="news", provider="x", retrieved_at=NAIVE, quality="fresh")
    with pytest.raises(ValidationError):
        FundamentalsSnapshot(
            symbol="AAPL",
            provider="sec",
            retrieved_at=NOW,
            quality=q,
            revenue=float("nan"),
        )
    with pytest.raises(ValidationError):
        MacroObservation(
            series_id="DGS10",
            value=float("inf"),
            observation_date=date(2026, 11, 13),
            quality=q,
        )
    with pytest.raises(ValidationError):
        CrossCheckClose(session_date=date(2026, 11, 13), adjusted_close=0)
    with pytest.raises(ValidationError):
        FilingsSnapshot(
            symbol="AAPL",
            items=[],
            provider="sec",
            retrieved_at=NOW,
            quality=q,
            insider_filing_count=-1,
        )
