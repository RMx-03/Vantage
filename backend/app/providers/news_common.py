"""Shared item building for the company-news providers.

Both providers apply the same window, text cleaning, hashing and ordering rules, so the
rules live here once. Nothing in this module logs or raises with provider content.
"""

import hashlib
import html
import re
from collections.abc import Sequence
from datetime import datetime, timedelta

from app.domain.research import (
    ComponentQuality,
    EvidenceDetails,
    NewsItem,
    NewsSnapshot,
)
from app.domain.urls import normalize_url

ERROR_CODE = "NEWS_PROVIDER_FAILED"
MESSAGES = {
    "auth": "News provider refused the configured credentials.",
    "rate_limited": "News provider rate limit was reached.",
    "unavailable": "Company news could not be retrieved.",
    "rejected": "Company news could not be retrieved.",
    "not_found": "Company news could not be retrieved.",
    "malformed": "Company news could not be retrieved.",
}
SUMMARY_LIMIT = 2000

_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_TAG = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")


def clean_summary(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = _SCRIPT_STYLE.sub(" ", value)
    text = html.unescape(_TAG.sub(" ", text))
    text = _SPACE.sub(" ", text.replace("\xa0", " ")).strip()[:SUMMARY_LIMIT].strip()
    return text or None


def upper_symbols(values: Sequence[object]) -> list[str]:
    return [s for v in values if (s := str(v).strip().upper())]


def build_item(
    *,
    provider: str,
    raw_id: object,
    publisher: object,
    title: object,
    summary: object,
    url: object,
    event_time: datetime,
    symbols: list[str],
    retrieved_at: datetime,
) -> NewsItem | None:
    """One evidence item, or None when it lacks an id or a non-empty title."""
    if raw_id is None or isinstance(raw_id, bool) or not str(raw_id).strip():
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    clean_title = title.strip()
    clean_publisher = (
        publisher.strip() if isinstance(publisher, str) and publisher.strip() else None
    )
    digest = hashlib.sha256(
        f"{(clean_publisher or '').lower()}|{clean_title.lower()}"
        f"|{event_time.isoformat()}".encode()
    ).hexdigest()
    return NewsItem(
        evidence_id=f"{provider}-{str(raw_id).strip()}",
        provider=provider,
        publisher=clean_publisher,
        title=clean_title,
        url=normalize_url(url) if isinstance(url, str) else None,
        event_time=event_time,
        retrieved_at=retrieved_at,
        content_hash=digest,
        summary=clean_summary(summary),
        details=EvidenceDetails(providers=[provider], tagged_symbols=symbols),
    )


def build_snapshot(
    *,
    provider: str,
    symbol: str,
    items: list[NewsItem],
    cutoff: datetime,
    retrieved_at: datetime,
    lookback_days: int,
    limit: int,
) -> NewsSnapshot:
    """Apply the shared window, ordering and limit, then wrap the result."""
    window_start = cutoff - timedelta(days=lookback_days)
    seen: set[str] = set()
    timed: list[tuple[float, str, NewsItem]] = []
    for item in items:
        moment = item.event_time
        if moment is None or not window_start < moment <= cutoff:
            continue
        if item.evidence_id in seen:
            continue
        seen.add(item.evidence_id)
        timed.append((-moment.timestamp(), item.evidence_id, item))
    timed.sort(key=lambda row: (row[0], row[1]))
    kept = [row[2] for row in timed][: max(limit, 0)]
    return NewsSnapshot(
        symbol=symbol,
        items=kept,
        provider=provider,
        retrieved_at=retrieved_at,
        coverage_start=window_start,
        coverage_end=cutoff,
        quality=ComponentQuality.FRESH if kept else ComponentQuality.MISSING,
        error_code=None,
    )
