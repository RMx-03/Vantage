import json
from datetime import UTC, datetime

from app.domain.research import (
    ComponentQuality,
    EvidenceDetails,
    NewsItem,
    NewsSnapshot,
)
from app.prompts.research_interpretation import build_interpretation_input

V2_EVIDENCE_KEYS = {
    "event_time",
    "evidence_id",
    "provider",
    "publisher",
    "retrieved_at",
    "title",
    "url",
}


def _news(**extra: object) -> NewsSnapshot:
    moment = datetime(2026, 11, 13, 21, 0, tzinfo=UTC)
    item = NewsItem(
        evidence_id="news-1",
        provider="yfinance",
        publisher="Wire",
        title="Headline",
        url="https://example.test/a",
        event_time=moment,
        retrieved_at=moment,
        content_hash="a" * 64,
        **extra,  # type: ignore[arg-type]
    )
    return NewsSnapshot(
        symbol="AAPL",
        items=[item],
        provider="yfinance",
        retrieved_at=moment,
        quality=ComponentQuality.FRESH,
    )


def test_v2_evidence_keys_are_pinned() -> None:
    payload = build_interpretation_input("AAPL", [], _news())
    assert set(payload["evidence"][0]) == V2_EVIDENCE_KEYS


def test_v2_evidence_ignores_multi_source_fields() -> None:
    news = _news(
        source_type="filing",
        summary="extra",
        details=EvidenceDetails(form_type="8-K"),
    )
    payload = build_interpretation_input("AAPL", [], news)
    assert set(payload["evidence"][0]) == V2_EVIDENCE_KEYS


def test_v2_evidence_serialization_matches_base() -> None:
    payload = build_interpretation_input("AAPL", [], _news())
    assert json.dumps(payload["evidence"], sort_keys=True) == json.dumps(
        [
            {
                "evidence_id": "news-1",
                "provider": "yfinance",
                "publisher": "Wire",
                "title": "Headline",
                "url": "https://example.test/a",
                "event_time": "2026-11-13T21:00:00Z",
                "retrieved_at": "2026-11-13T21:00:00Z",
            }
        ],
        sort_keys=True,
    )
