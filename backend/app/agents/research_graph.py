from typing import Any

from langgraph.graph import END, StateGraph

from app.domain.errors import VantageError
from app.domain.research import AIInterpretation
from app.models.state import ResearchState
from app.providers.contracts import InterpretationProvider
from app.services.metrics import calculate_metrics
from app.services.policy import apply_policy
from app.telemetry.tracing import get_tracer


def create_research_graph(interpretation_provider: InterpretationProvider):
    def calculate_metrics_node(state: ResearchState) -> dict[str, Any]:
        tracer = get_tracer()
        with tracer.start_as_current_span("calculate_metrics") as span:
            if "run_id" in state:
                span.set_attribute("vantage.run_id", str(state["run_id"]))
            metrics = calculate_metrics(state["market"])
            return {"metrics": metrics}

    def generate_interpretation_node(state: ResearchState) -> dict[str, Any]:
        tracer = get_tracer()
        run_id_str = str(state.get("run_id", ""))
        with tracer.start_as_current_span("generate_interpretation") as span:
            if run_id_str:
                span.set_attribute("vantage.run_id", run_id_str)
            with tracer.start_as_current_span("build_prompt") as p_span:
                if run_id_str:
                    p_span.set_attribute("vantage.run_id", run_id_str)

            with tracer.start_as_current_span("llm_generation") as g_span:
                if run_id_str:
                    g_span.set_attribute("vantage.run_id", run_id_str)
                try:
                    interp = interpretation_provider.interpret(
                        symbol=state["symbol"],
                        metrics=state.get("metrics", []),
                        news=state["news"],
                    )
                    failure_code = None
                except VantageError as exc:
                    interp = AIInterpretation(
                        sentiment_label="unavailable",
                        sentiment_score=None,
                        summary="AI interpretation was unavailable for this research run.",
                        evidence_ids=[],
                        warnings=["AI interpretation failed or was unavailable."],
                        abstained=True,
                        abstention_reason=exc.code,
                    )
                    failure_code = exc.code

            with tracer.start_as_current_span("validate_structured_output") as v_span:
                if run_id_str:
                    v_span.set_attribute("vantage.run_id", run_id_str)

            return {"interpretation": interp, "model_failure_code": failure_code}

    def apply_research_policy_node(state: ResearchState) -> dict[str, Any]:
        tracer = get_tracer()
        with tracer.start_as_current_span("apply_research_policy") as span:
            if "run_id" in state:
                span.set_attribute("vantage.run_id", str(state["run_id"]))
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
