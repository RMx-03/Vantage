"""Merge and de-duplicate news from several providers into one snapshot."""

import re
from collections.abc import Sequence
from datetime import timedelta
from urllib.parse import urlparse, urlunparse

from app.domain.research import (
    ComponentQuality,
    EvidenceDetails,
    NewsItem,
    NewsSnapshot,
)
from app.domain.urls import normalize_url

_TITLE_WINDOW = timedelta(hours=24)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def canonical_url(url: str | None) -> str | None:
    """`normalize_url`, plus a dropped leading ``www.`` on the host."""
    normalized = normalize_url(url)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    host = parsed.netloc.removeprefix("www.")
    if not host:
        return None
    return urlunparse(parsed._replace(netloc=host))


def normalize_title(title: str) -> str:
    return _NON_ALNUM.sub(" ", title.lower()).strip()


def _same_story(candidate: NewsItem, kept: NewsItem) -> bool:
    cand_url = canonical_url(candidate.url)
    if cand_url is not None and cand_url == canonical_url(kept.url):
        return True
    if candidate.event_time is None or kept.event_time is None:
        return False
    return (
        normalize_title(candidate.title) == normalize_title(kept.title)
        and abs(candidate.event_time - kept.event_time) <= _TITLE_WINDOW
    )


def _providers_of(item: NewsItem) -> list[str]:
    if item.details is not None and item.details.providers:
        return list(item.details.providers)
    return [item.provider]


def _dedupe(snapshots: Sequence[NewsSnapshot]) -> list[NewsItem]:
    walk: list[tuple[NewsItem, int, int]] = []
    position = 0
    for index, snapshot in enumerate(snapshots):
        if snapshot.quality == ComponentQuality.FAILED:
            continue
        for item in snapshot.items:
            walk.append((item, index, position))
            position += 1
    walk.sort(
        key=lambda t: (
            t[0].event_time is None,
            t[0].event_time.timestamp() if t[0].event_time else 0.0,
            t[1],
            t[2],
        )
    )
    kept: list[NewsItem] = []
    for item, _index, _pos in walk:
        for i, existing in enumerate(kept):
            if _same_story(item, existing):
                union = _providers_of(existing)
                union.extend(p for p in _providers_of(item) if p not in union)
                details = (existing.details or EvidenceDetails()).model_copy(
                    update={"providers": union}
                )
                kept[i] = existing.model_copy(update={"details": details})
                break
        else:
            kept.append(item)
    return kept


def merge_news(
    snapshots: Sequence[NewsSnapshot], *, symbol: str, limit: int
) -> NewsSnapshot:
    if len(snapshots) == 1:
        return snapshots[0]

    items = _dedupe(snapshots)
    items.sort(
        key=lambda i: (
            i.event_time is None,
            -(i.event_time.timestamp()) if i.event_time else 0.0,
            i.evidence_id,
        )
    )

    succeeded = [s for s in snapshots if s.quality != ComponentQuality.FAILED]
    failed_count = len(snapshots) - len(succeeded)
    error_code: str | None = None
    if not succeeded:
        quality = ComponentQuality.FAILED
        error_code = "NEWS_PROVIDER_FAILED"
    elif failed_count:
        quality = ComponentQuality.PARTIAL
        error_code = "PARTIAL_NEWS_COVERAGE"
    elif any(s.quality == ComponentQuality.PARTIAL for s in succeeded):
        quality = ComponentQuality.PARTIAL
    elif all(s.quality == ComponentQuality.MISSING for s in succeeded):
        quality = ComponentQuality.MISSING
    else:
        quality = ComponentQuality.FRESH

    starts = [s.coverage_start for s in snapshots if s.coverage_start is not None]
    ends = [s.coverage_end for s in snapshots if s.coverage_end is not None]
    return NewsSnapshot(
        symbol=symbol,
        items=items[:limit],
        provider=",".join(s.provider for s in snapshots),
        retrieved_at=max(s.retrieved_at for s in snapshots),
        coverage_start=min(starts) if starts else None,
        coverage_end=max(ends) if ends else None,
        quality=quality,
        error_code=error_code,
    )
