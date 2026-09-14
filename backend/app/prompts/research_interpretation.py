from typing import Any

from app.domain.research import AIInterpretation, NewsSnapshot, ResearchMetric

PROMPT_VERSION = "research-interpretation-v1"
SYSTEM_INSTRUCTION = (
    "You summarize supplied historical US-equity research facts. "
    "Use only supplied metrics and evidence IDs. Do not give investment advice, "
    "predict returns, invent numbers, sources, thresholds, or reason codes. "
    "If evidence is inadequate, abstain."
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
