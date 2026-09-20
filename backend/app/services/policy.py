from typing import Literal

from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DataQuality,
    MarketSnapshot,
    ModelQuality,
    NewsSnapshot,
    OverallQuality,
    Reason,
    ResearchMetric,
    ResearchStatus,
    StrictModel,
)
from app.services.quality import assess_quality

POLICY_VERSION: Literal["research-policy-v1"] = "research-policy-v1"
VOLATILITY_THRESHOLD: float = 0.40

REASON_ORDER: dict[str, int] = {
    "MARKET_DATA_PROVIDER_FAILED": 0,
    "INVALID_PRICE_SERIES": 1,
    "STALE_PRICE_DATA": 2,
    "INSUFFICIENT_PRICE_HISTORY": 3,
    "NEWS_PROVIDER_FAILED": 10,
    "NO_RECENT_NEWS": 11,
    "PARTIAL_NEWS_COVERAGE": 12,
    "MODEL_UNAVAILABLE": 13,
    "MODEL_OUTPUT_INVALID": 14,
    "ELEVATED_VOLATILITY": 20,
    "NEGATIVE_NEWS_SENTIMENT": 21,
}


class PolicyResult(StrictModel):
    research_status: ResearchStatus
    summary: str
    reasons: list[Reason]
    metrics: list[ResearchMetric]
    data_quality: DataQuality
    warnings: list[str]
    interpretation: AIInterpretation


def order_reasons(reasons: list[Reason]) -> list[Reason]:
    severity = {"blocking": 0, "warning": 1, "info": 2}
    return sorted(
        reasons,
        key=lambda item: (
            severity.get(item.severity, 99),
            REASON_ORDER.get(item.code, 99),
        ),
    )


def collect_registered_reasons(
    market: MarketSnapshot,
    news: NewsSnapshot,
    interpretation: AIInterpretation,
    metrics: list[ResearchMetric],
) -> list[Reason]:
    reasons: list[Reason] = []

    # 1. Market blocking reasons
    if market.error_code == "MARKET_DATA_PROVIDER_FAILED" or (
        market.quality == ComponentQuality.FAILED
        and market.error_code != "INVALID_PRICE_SERIES"
    ):
        reasons.append(
            Reason(
                code="MARKET_DATA_PROVIDER_FAILED",
                label="Market Data Provider Failed",
                severity="blocking",
                description="Unable to fetch market data from the upstream provider.",
                policy_version=POLICY_VERSION,
            )
        )

    if market.error_code == "INVALID_PRICE_SERIES":
        reasons.append(
            Reason(
                code="INVALID_PRICE_SERIES",
                label="Invalid Price Series",
                severity="blocking",
                description="Market price series failed numerical integrity or ordering checks.",
                policy_version=POLICY_VERSION,
            )
        )

    if market.quality == ComponentQuality.STALE or (
        market.bars and market.bars[-1].session_date != market.latest_completed_session
    ):
        reasons.append(
            Reason(
                code="STALE_PRICE_DATA",
                label="Stale Price Data",
                severity="blocking",
                description="Latest accepted price bar does not match the latest completed session.",
                policy_version=POLICY_VERSION,
            )
        )

    if market.error_code is None and len(market.bars) < 21:
        reasons.append(
            Reason(
                code="INSUFFICIENT_PRICE_HISTORY",
                label="Insufficient Price History",
                severity="blocking",
                description="Fewer than 21 daily sessions are available for metric calculation.",
                metric_keys=["price_observation_count"],
                policy_version=POLICY_VERSION,
            )
        )

    # 2. News warning reasons
    if (
        news.quality == ComponentQuality.FAILED
        or news.error_code == "NEWS_PROVIDER_FAILED"
    ):
        reasons.append(
            Reason(
                code="NEWS_PROVIDER_FAILED",
                label="News Provider Failed",
                severity="warning",
                description="Upstream news provider request failed or timed out.",
                policy_version=POLICY_VERSION,
            )
        )

    if news.quality == ComponentQuality.MISSING or len(news.items) == 0:
        reasons.append(
            Reason(
                code="NO_RECENT_NEWS",
                label="No Recent News",
                severity="warning",
                description="No relevant news articles were found within the recent observation window.",
                policy_version=POLICY_VERSION,
            )
        )
    elif news.quality == ComponentQuality.PARTIAL:
        reasons.append(
            Reason(
                code="PARTIAL_NEWS_COVERAGE",
                label="Partial News Coverage",
                severity="warning",
                description="News items were partially retrieved or had incomplete publisher diversity.",
                policy_version=POLICY_VERSION,
            )
        )

    # 3. Model warning reasons
    if interpretation.abstention_reason != "MODEL_NOT_RUN" and (
        interpretation.abstained or interpretation.sentiment_label == "unavailable"
    ):
        if interpretation.abstention_reason == "MODEL_UNAVAILABLE":
            reasons.append(
                Reason(
                    code="MODEL_UNAVAILABLE",
                    label="Model Unavailable",
                    severity="warning",
                    description="AI model provider was unavailable or timed out.",
                    policy_version=POLICY_VERSION,
                )
            )
        else:
            reasons.append(
                Reason(
                    code="MODEL_OUTPUT_INVALID",
                    label="Model Output Invalid",
                    severity="warning",
                    description="AI model response failed schema validation or safety policy.",
                    policy_version=POLICY_VERSION,
                )
            )

    # 4. Metric warning reasons
    for metric in metrics:
        if metric.key == "annualized_volatility_20" and metric.value is not None:
            if metric.value >= VOLATILITY_THRESHOLD:
                reasons.append(
                    Reason(
                        code="ELEVATED_VOLATILITY",
                        label="Elevated Volatility",
                        severity="warning",
                        description=f"20-session annualized volatility ({metric.value:.1%}) exceeds the {VOLATILITY_THRESHOLD:.1%} policy threshold.",
                        metric_keys=["annualized_volatility_20"],
                        policy_version=POLICY_VERSION,
                        threshold=VOLATILITY_THRESHOLD,
                    )
                )

    if interpretation.sentiment_label == "negative" or (
        interpretation.sentiment_score is not None
        and interpretation.sentiment_score < 0.0
    ):
        score_repr = (
            f" (score: {interpretation.sentiment_score:.2f})"
            if interpretation.sentiment_score is not None
            else ""
        )
        reasons.append(
            Reason(
                code="NEGATIVE_NEWS_SENTIMENT",
                label="Negative News Sentiment",
                severity="warning",
                description=f"Qualitative interpretation identified negative news sentiment{score_repr}.",
                evidence_ids=interpretation.evidence_ids,
                policy_version=POLICY_VERSION,
                threshold=0.0,
            )
        )

    return reasons


def deterministic_summary(
    status: ResearchStatus, reasons: list[Reason], metrics: list[ResearchMetric]
) -> str:
    if status == ResearchStatus.INSUFFICIENT_DATA:
        blocking = [r.label for r in reasons if r.severity == "blocking"]
        block_text = (
            "; ".join(blocking) if blocking else "required inputs are unavailable"
        )
        return f"Research run insufficient data: {block_text}."

    if status == ResearchStatus.REVIEW:
        warnings = [r.label for r in reasons if r.severity == "warning"]
        warn_text = (
            "; ".join(warnings)
            if warnings
            else "input quality or model interpretation degraded"
        )
        return f"Research run requires review: {warn_text}."

    return "Research run completed successfully with sufficient quality and no active warnings."


def apply_policy(
    market: MarketSnapshot,
    news: NewsSnapshot,
    interpretation: AIInterpretation,
    metrics: list[ResearchMetric],
) -> PolicyResult:
    reasons = collect_registered_reasons(market, news, interpretation, metrics)
    quality = assess_quality(market, news, interpretation)

    if quality.overall == OverallQuality.INSUFFICIENT:
        status = ResearchStatus.INSUFFICIENT_DATA
    elif quality.overall == OverallQuality.DEGRADED or any(
        r.severity == "warning" for r in reasons
    ):
        status = ResearchStatus.REVIEW
    else:
        status = ResearchStatus.INFORMATIONAL

    ordered = order_reasons(reasons)
    warnings = [r.description for r in ordered if r.severity == "warning"] + list(
        interpretation.warnings
    )
    summary = deterministic_summary(status, ordered, metrics)

    return PolicyResult(
        research_status=status,
        summary=summary,
        reasons=ordered,
        metrics=metrics,
        data_quality=quality,
        warnings=warnings,
        interpretation=interpretation,
    )
