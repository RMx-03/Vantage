import hashlib
import json
from collections.abc import Sequence
from typing import Any

from app.domain.research import (
    DailyBar,
    FundamentalsSnapshot,
    MacroSnapshot,
    MarketSnapshot,
    NewsItem,
    NewsSnapshot,
)


def bar_fields(bar: DailyBar) -> dict[str, Any]:
    return {
        "session_date": bar.session_date.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "adjusted_close": bar.adjusted_close,
        "volume": bar.volume,
        "currency": bar.currency,
        "adjustment_state": bar.adjustment_state,
    }


def _without_retrieved_at(value: Any) -> Any:
    """Retrieval time is not content; drop it at every nesting level."""
    if isinstance(value, dict):
        return {
            key: _without_retrieved_at(item)
            for key, item in value.items()
            if key != "retrieved_at"
        }
    if isinstance(value, list):
        return [_without_retrieved_at(item) for item in value]
    return value


def combined_snapshot_hash(
    market: MarketSnapshot,
    news: NewsSnapshot,
    *,
    evidence: Sequence[NewsItem] | None = None,
    fundamentals: FundamentalsSnapshot | None = None,
    macro: MacroSnapshot | None = None,
) -> str:
    """Hash accepted inputs independent of provider item ordering.

    New inputs (context bars, fundamentals, macro, richer news fields) enter the
    payload only when present, so existing-shape snapshots hash as they always did.
    """
    news_items: list[dict[str, Any]] = []
    for item in sorted(
        news.items if evidence is None else evidence,
        key=lambda value: value.evidence_id,
    ):
        entry: dict[str, Any] = {
            "evidence_id": item.evidence_id,
            "provider": item.provider,
            "publisher": item.publisher,
            "title": item.title,
            "url": item.url,
            "event_time": item.event_time.isoformat() if item.event_time else None,
            "content_hash": item.content_hash,
        }
        if item.source_type != "news":
            entry["source_type"] = item.source_type
        if item.summary is not None:
            entry["summary"] = item.summary
        if item.details is not None:
            entry["details"] = item.details.model_dump(mode="json")
        news_items.append(entry)
    payload: dict[str, Any] = {
        "symbol": market.symbol,
        "market_content_hash": market.content_hash,
        "market_quality": market.quality.value,
        "market_volume_quality": market.volume_quality.value,
        "market_error_code": market.error_code,
        "market_missing_value_count": market.missing_value_count,
        "market_duplicate_session_count": market.duplicate_session_count,
        "news_provider": news.provider,
        "news_quality": news.quality.value,
        "news_error_code": news.error_code,
        "news_coverage_start": (
            news.coverage_start.isoformat() if news.coverage_start else None
        ),
        "news_coverage_end": news.coverage_end.isoformat()
        if news.coverage_end
        else None,
        "news_items": news_items,
    }
    if market.context_bars:
        payload["context_bars"] = {
            symbol: [
                bar_fields(bar)
                for bar in sorted(
                    market.context_bars[symbol], key=lambda b: b.session_date
                )
            ]
            for symbol in sorted(market.context_bars)
        }
    if fundamentals is not None:
        payload["fundamentals"] = _without_retrieved_at(
            fundamentals.model_dump(mode="json")
        )
    if macro is not None:
        ordered = macro.model_copy(
            update={
                "observations": sorted(macro.observations, key=lambda o: o.series_id)
            }
        )
        payload["macro"] = _without_retrieved_at(ordered.model_dump(mode="json"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
