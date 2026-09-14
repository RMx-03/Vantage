from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DataQuality,
    MarketSnapshot,
    ModelQuality,
    NewsSnapshot,
    OverallQuality,
)


def assess_quality(
    market: MarketSnapshot, news: NewsSnapshot, interpretation: AIInterpretation
) -> DataQuality:
    # 1. Price Quality
    if market.quality == ComponentQuality.FAILED or market.error_code is not None:
        prices_quality = ComponentQuality.FAILED
    elif len(market.bars) < 21:
        prices_quality = ComponentQuality.PARTIAL
    elif market.quality == ComponentQuality.STALE or (
        market.bars and market.bars[-1].session_date != market.latest_completed_session
    ):
        prices_quality = ComponentQuality.STALE
    else:
        prices_quality = ComponentQuality.FRESH

    # 2. News Quality
    if news.quality == ComponentQuality.FAILED or news.error_code is not None:
        news_quality = ComponentQuality.FAILED
    elif news.quality == ComponentQuality.MISSING or len(news.items) == 0:
        news_quality = ComponentQuality.MISSING
    elif news.quality == ComponentQuality.PARTIAL:
        news_quality = ComponentQuality.PARTIAL
    elif news.quality == ComponentQuality.STALE:
        news_quality = ComponentQuality.STALE
    else:
        news_quality = ComponentQuality.FRESH

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
