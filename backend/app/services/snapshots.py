import hashlib
import json
from typing import Any

from app.domain.research import MarketSnapshot, NewsSnapshot


def combined_snapshot_hash(market: MarketSnapshot, news: NewsSnapshot) -> str:
    """Hash accepted market and news content independent of provider item ordering."""
    news_items: list[dict[str, Any]] = []
    for item in sorted(news.items, key=lambda value: value.evidence_id):
        news_items.append(
            {
                "evidence_id": item.evidence_id,
                "provider": item.provider,
                "publisher": item.publisher,
                "title": item.title,
                "url": item.url,
                "event_time": item.event_time.isoformat() if item.event_time else None,
                "content_hash": item.content_hash,
            }
        )
    payload = {
        "symbol": market.symbol,
        "market_content_hash": market.content_hash,
        "market_quality": market.quality.value,
        "market_error_code": market.error_code,
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
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
