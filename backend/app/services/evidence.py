"""Merge and de-duplicate news from several providers into one snapshot."""

import re
from collections.abc import Sequence
from datetime import timedelta
from urllib.parse import urlparse, urlunparse

from app.domain.research import (
    ComponentQuality,
    EvidenceDetails,
    FilingsSnapshot,
    NewsItem,
    NewsSnapshot,
)
from app.domain.urls import normalize_url

_TITLE_WINDOW = timedelta(hours=24)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

EVIDENCE_FILING_LIMIT = 10
EVIDENCE_INSIDER_LIMIT = 10
_MAX_TAGGED_SYMBOLS = 3
_MIN_NAME_LENGTH = 3

_STATE_MARKER = re.compile(r"\s*/[A-Za-z]{2}/?\s*$")
_SUFFIXES = (
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "plc",
    "llc",
    "lp",
    "nv",
    "sa",
    "ag",
    "se",
)
_SUFFIX = re.compile(
    r"(?:[\s,]+&)?[\s,]+(?:"
    + "|".join(r"\.?".join(suffix) for suffix in _SUFFIXES)
    + r")\.?\s*$",
    re.IGNORECASE,
)


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
    cand_title = normalize_title(candidate.title)
    return (
        # A title with no ASCII alphanumerics normalises to "": never a match.
        bool(cand_title)
        and cand_title == normalize_title(kept.title)
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
        # No error code: quality.py reads any news error code as FAILED. Policy v1
        # derives PARTIAL_NEWS_COVERAGE from the partial quality.
        quality = ComponentQuality.PARTIAL
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


def company_search_name(name: str | None) -> str | None:
    """The EDGAR name without a state marker or trailing legal suffixes."""
    if name is None:
        return None
    result = _STATE_MARKER.sub("", name).strip(" ,")
    while True:
        stripped = _SUFFIX.sub("", result).strip(" ,")
        if stripped == result:
            break
        result = stripped
    result = result.strip(" ,&")
    return result if len(result) >= _MIN_NAME_LENGTH else None


def _share_class(symbol: str) -> str:
    return symbol.strip().upper().replace("-", ".")


def _whole(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9])(?:{pattern})(?![A-Za-z0-9])", flags)


def _mentions_ticker(text: str, symbol: str) -> bool:
    ticker = symbol.strip().upper()
    if len(ticker) < 2:
        return False
    forms = {ticker, ticker.replace(".", "-"), ticker.replace("-", ".")}
    return (
        _whole("|".join(re.escape(f) for f in sorted(forms))).search(text) is not None
    )


def is_company_specific(
    item: NewsItem, *, symbol: str, company_name: str | None
) -> bool:
    """Whether an evidence item is about the company itself, decided in code."""
    if item.source_type in ("filing", "insider_transaction"):
        return True
    if item.details is None:
        return False
    tagged = [_share_class(t) for t in item.details.tagged_symbols]
    if (
        not 1 <= len(tagged) <= _MAX_TAGGED_SYMBOLS
        or _share_class(symbol) not in tagged
    ):
        return False
    text = f"{item.title}\n{item.summary or ''}"
    if _mentions_ticker(text, symbol):
        return True
    search_name = company_search_name(company_name)
    return (
        search_name is not None
        and _whole(re.escape(search_name), re.IGNORECASE).search(text) is not None
    )


def _recency_key(item: NewsItem) -> tuple[bool, float, str]:
    return (
        item.event_time is None,
        -(item.event_time.timestamp()) if item.event_time else 0.0,
        item.evidence_id,
    )


def assemble_evidence(
    news: NewsSnapshot, filings: FilingsSnapshot | None, *, symbol: str
) -> list[NewsItem]:
    """One evidence list: merged news, recent filings and recent insider filings."""
    company_name: str | None = None
    selected: list[NewsItem] = list(news.items)
    if filings is not None and filings.quality not in (
        ComponentQuality.FAILED,
        ComponentQuality.MISSING,
    ):
        company_name = filings.company_name
        filing_items = sorted(
            (i for i in filings.items if i.source_type == "filing"), key=_recency_key
        )
        insider_items = sorted(
            (
                i
                for i in filings.items
                if i.source_type == "insider_transaction"
                and not (i.details and i.details.parse_state == "not_fetched")
            ),
            key=_recency_key,
        )
        selected += filing_items[:EVIDENCE_FILING_LIMIT]
        selected += insider_items[:EVIDENCE_INSIDER_LIMIT]

    flagged: list[NewsItem] = []
    for item in selected:
        value = is_company_specific(item, symbol=symbol, company_name=company_name)
        details = (item.details or EvidenceDetails()).model_copy(
            update={"company_specific": value}
        )
        flagged.append(item.model_copy(update={"details": details}))
    flagged.sort(key=_recency_key)
    return flagged
