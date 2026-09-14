from typing import Any

from langgraph.graph import END, StateGraph

from app.domain.errors import VantageError
from app.domain.research import AIInterpretation
from app.models.state import ResearchState
from app.providers.contracts import InterpretationProvider
from app.services.metrics import calculate_metrics
from app.services.policy import apply_policy


def create_research_graph(interpretation_provider: InterpretationProvider):
    def calculate_metrics_node(state: ResearchState) -> dict[str, Any]:
        metrics = calculate_metrics(state["market"])
        return {"metrics": metrics}

    def generate_interpretation_node(state: ResearchState) -> dict[str, Any]:
        try:
            interp = interpretation_provider.interpret(
                symbol=state["symbol"],
                metrics=state.get("metrics", []),
                news=state["news"],
            )
            return {"interpretation": interp, "model_failure_code": None}
        except VantageError as exc:
            fallback = AIInterpretation(
                sentiment_label="unavailable",
                sentiment_score=None,
                summary="AI interpretation was unavailable for this research run.",
                evidence_ids=[],
                warnings=["AI interpretation failed or was unavailable."],
                abstained=True,
                abstention_reason=exc.code,
            )
            return {"interpretation": fallback, "model_failure_code": exc.code}

    def apply_research_policy_node(state: ResearchState) -> dict[str, Any]:
        policy_result = apply_policy(
            market=state["market"],
            news=state["news"],
            interpretation=state["interpretation"],
            metrics=state.get("metrics", []),
        )
        return {"policy": policy_result}

    builder = StateGraph(ResearchState)
    builder.add_node("calculate_metrics", calculate_metrics_node)
    builder.add_node("generate_interpretation", generate_interpretation_node)
    builder.add_node("apply_research_policy", apply_research_policy_node)
    builder.set_entry_point("calculate_metrics")
    builder.add_edge("calculate_metrics", "generate_interpretation")
    builder.add_edge("generate_interpretation", "apply_research_policy")
    builder.add_edge("apply_research_policy", END)
    return builder.compile()
