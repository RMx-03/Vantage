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
    RoleQuality,
    StrictModel,
)
from app.services.data_stage import MARKET_CONTEXT_SYMBOL
from app.services.metrics import ROLE_METRIC_KEYS
from app.services.quality import assess_quality
from app.services.run_inputs import OPTIONAL_ROLES, RunInputs

POLICY_VERSION: Literal["research-policy-v2"] = "research-policy-v2"
CROSSCHECK_THRESHOLD: float = 0.01
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
    "FILINGS_PROVIDER_FAILED": 15,
    "PRICE_SOURCES_DISAGREE": 16,
    "PROVIDER_NOT_CONFIGURED": 17,
    "NO_SEC_FILER_RECORD": 18,
    "SECTOR_UNMAPPED": 19,
    "FUNDAMENTALS_UNAVAILABLE": 20,
    "FUNDAMENTALS_PARTIAL": 21,
    "MACRO_DATA_STALE": 22,
    "MACRO_DATA_PARTIAL": 23,
    "MACRO_PROVIDER_FAILED": 24,
    "PRICE_CROSSCHECK_UNAVAILABLE": 25,
    "CONTEXT_BARS_UNAVAILABLE": 26,
    "ELEVATED_VOLATILITY": 30,
    "NEGATIVE_NEWS_SENTIMENT": 31,
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
    inputs: RunInputs | None = None,
) -> list[Reason]:
    inputs = inputs if inputs is not None else RunInputs()
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

    # Not an elif: an empty merge can still hide a provider that failed.
    if news.quality == ComponentQuality.PARTIAL:
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

    reasons.extend(_input_reasons(market, metrics, inputs))
    return reasons


def _market_is_usable(market: MarketSnapshot) -> bool:
    return (
        market.error_code is None
        and market.quality == ComponentQuality.FRESH
        and len(market.bars) >= 21
        and market.bars[-1].session_date == market.latest_completed_session
    )


def _input_reasons(
    market: MarketSnapshot, metrics: list[ResearchMetric], inputs: RunInputs
) -> list[Reason]:
    reasons: list[Reason] = []

    def add(
        code: str,
        label: str,
        severity: Literal["info", "warning", "blocking"],
        description: str,
        metric_keys: list[str] | None = None,
        threshold: float | None = None,
    ) -> None:
        reasons.append(
            Reason(
                code=code,
                label=label,
                severity=severity,
                description=description,
                metric_keys=metric_keys or [],
                policy_version=POLICY_VERSION,
                threshold=threshold,
            )
        )

    role_names = {
        "filings": "SEC filings",
        "fundamentals": "Fundamentals",
        "macro": "Macro",
        "crosscheck": "Price cross-check",
    }
    quality = {role: inputs.role_quality(role) for role in OPTIONAL_ROLES}

    for role in OPTIONAL_ROLES:
        if quality[role] == RoleQuality.NOT_CONFIGURED:
            name = role_names[role]
            add(
                "PROVIDER_NOT_CONFIGURED",
                f"{name} Provider Not Configured",
                "info",
                f"No {name.lower()} provider is configured for this run; "
                "its metrics are unavailable.",
                list(ROLE_METRIC_KEYS[role]),
            )

    filings_failed = quality["filings"] == RoleQuality.FAILED
    fundamentals_failed = quality["fundamentals"] == RoleQuality.FAILED
    if filings_failed or fundamentals_failed:
        if fundamentals_failed and not filings_failed:
            edgar_description = (
                "SEC EDGAR fundamentals could not be retrieved; fundamentals "
                "metrics are unavailable."
            )
            edgar_keys = list(ROLE_METRIC_KEYS["fundamentals"])
        else:
            edgar_description = (
                "SEC EDGAR data could not be retrieved; filing and fundamentals "
                "metrics are unavailable."
            )
            edgar_keys = [
                *ROLE_METRIC_KEYS["filings"],
                *ROLE_METRIC_KEYS["fundamentals"],
            ]
        add(
            "FILINGS_PROVIDER_FAILED",
            "SEC Filings Provider Failed",
            "warning",
            edgar_description,
            edgar_keys,
        )

    if inputs.role_error("filings") == "NO_SEC_FILER_RECORD":
        add(
            "NO_SEC_FILER_RECORD",
            "No SEC Filer Record",
            "info",
            "No SEC filer record was found for this ticker; filing metrics are "
            "unavailable.",
            list(ROLE_METRIC_KEYS["filings"]),
        )

    if (
        inputs.filings is not None
        and inputs.filings.sic_code
        and inputs.sector_etf is None
        and quality["filings"] not in (RoleQuality.NOT_CONFIGURED, RoleQuality.FAILED)
    ):
        add(
            "SECTOR_UNMAPPED",
            "Sector Not Mapped",
            "info",
            "The company's SIC code does not map to a sector ETF; the sector "
            "excess-return metric is unavailable.",
            ["excess_return_20_vs_sector"],
        )

    if (
        inputs.filings is not None
        and not inputs.filings.sic_code
        and inputs.sector_etf is None
        and quality["filings"] not in (RoleQuality.NOT_CONFIGURED, RoleQuality.FAILED)
        and inputs.role_error("filings") != "NO_SEC_FILER_RECORD"
    ):
        add(
            "SECTOR_UNMAPPED",
            "Sector Not Mapped",
            "info",
            "No SEC industry code was available, so no sector ETF comparison "
            "was made; the sector excess-return metric is unavailable.",
            ["excess_return_20_vs_sector"],
        )

    if inputs.role_error("fundamentals") == "FUNDAMENTALS_UNAVAILABLE":
        add(
            "FUNDAMENTALS_UNAVAILABLE",
            "Fundamentals Unavailable",
            "info",
            "No annual (10-K) financial facts were found; fundamentals metrics "
            "are unavailable.",
            list(ROLE_METRIC_KEYS["fundamentals"]),
        )

    def missing_keys(role: str) -> list[str]:
        return [
            m.key
            for m in metrics
            if m.key in ROLE_METRIC_KEYS[role] and m.value is None
        ]

    if (
        inputs.fundamentals is not None
        and quality["fundamentals"]
        not in (RoleQuality.NOT_CONFIGURED, RoleQuality.FAILED)
        and inputs.fundamentals.quality == ComponentQuality.PARTIAL
        and (keys := missing_keys("fundamentals"))
    ):
        add(
            "FUNDAMENTALS_PARTIAL",
            "Fundamentals Partly Unavailable",
            "info",
            "Part of the latest annual SEC data was unavailable; the affected "
            "fundamentals metrics are unavailable.",
            keys,
        )

    if inputs.macro is not None and any(
        obs.quality == ComponentQuality.STALE for obs in inputs.macro.observations
    ):
        add(
            "MACRO_DATA_STALE",
            "Macro Data Stale",
            "info",
            "At least one macro series has an observation older than its "
            "freshness window.",
            list(ROLE_METRIC_KEYS["macro"]),
        )

    if (
        inputs.macro is not None
        and quality["macro"] not in (RoleQuality.NOT_CONFIGURED, RoleQuality.FAILED)
        and inputs.macro.quality == ComponentQuality.PARTIAL
        and (keys := missing_keys("macro"))
    ):
        add(
            "MACRO_DATA_PARTIAL",
            "Macro Data Partly Unavailable",
            "info",
            "Some macro series had no recent value; those macro metrics are "
            "unavailable.",
            keys,
        )

    if quality["macro"] == RoleQuality.FAILED:
        add(
            "MACRO_PROVIDER_FAILED",
            "Macro Provider Failed",
            "info",
            "Macro series could not be retrieved; macro metrics are unavailable.",
            list(ROLE_METRIC_KEYS["macro"]),
        )

    for metric in metrics:
        if (
            metric.key == "price_crosscheck_max_deviation"
            and metric.value is not None
            and metric.value > CROSSCHECK_THRESHOLD
        ):
            add(
                "PRICE_SOURCES_DISAGREE",
                "Price Sources Disagree",
                "warning",
                f"Adjusted closes differ between price sources by up to "
                f"{metric.value:.1%}, above the {CROSSCHECK_THRESHOLD:.1%} "
                "threshold.",
                ["price_crosscheck_max_deviation"],
                CROSSCHECK_THRESHOLD,
            )

    if quality["crosscheck"] in (RoleQuality.FAILED, RoleQuality.MISSING):
        add(
            "PRICE_CROSSCHECK_UNAVAILABLE",
            "Price Cross-Check Unavailable",
            "info",
            "The second price source returned no usable data; the price "
            "cross-check metric is unavailable.",
            list(ROLE_METRIC_KEYS["crosscheck"]),
        )

    if _market_is_usable(market):
        by_key = {metric.key: metric for metric in metrics}

        def unaligned(keys: list[str]) -> bool:
            # A context series that exists but shares no session with the run's
            # window leaves its relative metric with no value.
            present = [by_key[key] for key in keys if key in by_key]
            return any(m.value is None for m in present)

        market_keys = ["excess_return_5_vs_spy", "excess_return_20_vs_spy"]
        sector_keys = ["excess_return_20_vs_sector"]
        # A run for the benchmark itself has no benchmark comparison to make.
        wants_market = market.symbol != MARKET_CONTEXT_SYMBOL
        wants_sector = bool(inputs.sector_etf)
        market_gap = wants_market and (
            not market.context_bars.get(MARKET_CONTEXT_SYMBOL) or unaligned(market_keys)
        )
        sector_gap = wants_sector and (
            not market.context_bars.get(inputs.sector_etf or "")
            or unaligned(sector_keys)
        )
        if market_gap or sector_gap:
            add(
                "CONTEXT_BARS_UNAVAILABLE",
                "Context Price Bars Unavailable",
                "info",
                "Price bars for SPY or the sector ETF were not retrieved or did "
                "not line up with this symbol's sessions; relative-return "
                "metrics are unavailable.",
                (market_keys if market_gap else [])
                + (sector_keys if sector_gap else []),
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
    inputs: RunInputs | None = None,
) -> PolicyResult:
    reasons = collect_registered_reasons(market, news, interpretation, metrics, inputs)
    quality = assess_quality(market, news, interpretation, inputs)

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
