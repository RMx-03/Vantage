from typing import Any

from app.domain.research import AIInterpretation, NewsSnapshot, ResearchMetric

PROMPT_VERSION = "research-interpretation-v2"
SYSTEM_INSTRUCTION = (
    "You summarize supplied historical US-equity research facts. "
    "Use only supplied metrics and evidence IDs. In summary, every warning, and "
    "abstention_reason, do not include numeric claims, digits, or spelled-out "
    "numbers, even when supplied as input. The structured sentiment_score may "
    "be numeric; evidence IDs must be copied exactly. Do not invent sources, "
    "thresholds, or reason codes. Do not give investment advice or direct "
    "recommendations, including buy, sell, hold, or invest instructions or "
    "ratings. Do not personalize to a reader's portfolio, risk tolerance, "
    "financial situation, or goals; do not make suitability claims. Do not "
    "provide target prices, guarantees, risk-free claims, return predictions, "
    "or statements of certain future performance. Summarize historical "
    "observations only. If evidence is inadequate, abstain. When abstained is "
    "true, sentiment_label must be unavailable, sentiment_score must be null, "
    "evidence_ids must be empty, and abstention_reason must be exactly one of "
    "MODEL_NOT_RUN, MODEL_UNAVAILABLE, MODEL_OUTPUT_INVALID. When abstained is "
    "false, sentiment_label must not be unavailable, abstention_reason must be "
    "null, and evidence_ids must contain at least one supplied evidence ID. "
    "Every cited evidence ID must come from the supplied evidence."
)


def build_interpretation_input(
    symbol: str, metrics: list[ResearchMetric], news: NewsSnapshot
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "metrics": [metric.model_dump(mode="json") for metric in metrics],
        "evidence": [
            item.model_dump(mode="json", exclude={"content_hash"})
            for item in news.items
        ],
        "response_schema": AIInterpretation.model_json_schema(),
    }
