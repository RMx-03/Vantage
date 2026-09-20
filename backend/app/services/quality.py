from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DataQuality,
    MarketSnapshot,
    ModelQuality,
    NewsSnapshot,
    OverallQuality,
)

COMPONENT_QUALITY_SEVERITY: dict[ComponentQuality, int] = {
    ComponentQuality.FRESH: 0,
    ComponentQuality.PARTIAL: 1,
    ComponentQuality.STALE: 2,
    ComponentQuality.MISSING: 3,
    ComponentQuality.FAILED: 4,
}


def worse_component_quality(
    first: ComponentQuality, *others: ComponentQuality
) -> ComponentQuality:
    return max(
        (first, *others),
        key=lambda quality: COMPONENT_QUALITY_SEVERITY[quality],
    )


def assess_quality(
    market: MarketSnapshot, news: NewsSnapshot, interpretation: AIInterpretation
) -> DataQuality:
    # 1. Price Quality
    prices_quality = market.quality
    if market.error_code is not None:
        prices_quality = worse_component_quality(
            prices_quality, ComponentQuality.FAILED
        )
    if len(market.bars) < 21:
        prices_quality = worse_component_quality(
            prices_quality, ComponentQuality.PARTIAL
        )
    if market.bars and market.bars[-1].session_date != market.latest_completed_session:
        prices_quality = worse_component_quality(prices_quality, ComponentQuality.STALE)

    # 2. News Quality
    news_quality = news.quality
    if news.error_code is not None:
        news_quality = worse_component_quality(news_quality, ComponentQuality.FAILED)
    if not news.items:
        news_quality = worse_component_quality(news_quality, ComponentQuality.MISSING)

    # 3. Model Quality
    if interpretation.abstention_reason == "MODEL_NOT_RUN":
        model_quality = ModelQuality.NOT_RUN
    elif interpretation.abstained or interpretation.sentiment_label == "unavailable":
        model_quality = ModelQuality.FAILED
    elif interpretation.warnings:
        model_quality = ModelQuality.DEGRADED
    else:
        model_quality = ModelQuality.HEALTHY

    # 4. Overall Quality
    if (
        prices_quality
        in (ComponentQuality.FAILED, ComponentQuality.STALE, ComponentQuality.MISSING)
        or len(market.bars) < 21
    ):
        overall_quality = OverallQuality.INSUFFICIENT
    elif (
        prices_quality != ComponentQuality.FRESH
        or news_quality
        in (
            ComponentQuality.PARTIAL,
            ComponentQuality.MISSING,
            ComponentQuality.STALE,
            ComponentQuality.FAILED,
        )
        or model_quality in (ModelQuality.DEGRADED, ModelQuality.FAILED)
    ):
        overall_quality = OverallQuality.DEGRADED
    else:
        overall_quality = OverallQuality.SUFFICIENT

    return DataQuality(
        overall=overall_quality,
        prices=prices_quality,
        news=news_quality,
        model=model_quality,
    )
