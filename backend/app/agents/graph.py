import logging

from langgraph.graph import END, StateGraph

from app.agents.analyst import run_analyst
from app.agents.quant_risk import run_quant_risk
from app.agents.scraper import run_scraper
from app.models.state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build the agent graph
# ---------------------------------------------------------------------------

_builder = StateGraph(AgentState)

_builder.add_node("scraper", run_scraper)
_builder.add_node("analyst", run_analyst)
_builder.add_node("quant_risk", run_quant_risk)

_builder.set_entry_point("scraper")

_builder.add_edge("scraper", "analyst")
_builder.add_edge("analyst", "quant_risk")
_builder.add_edge("quant_risk", END)

# Compiled workflow — module-level singleton, built once on import
workflow = _builder.compile()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_analysis(ticker: str) -> AgentState:
    """
    Execute the full Vantage analysis pipeline for a given ticker.

    Pipeline: Scraper -> Analyst -> QuantRisk -> END

    Each node receives the full AgentState and returns a partial dict
    containing only the fields it updates. LangGraph merges these
    partial updates into the running state automatically.

    Args:
        ticker: Stock ticker symbol (must already be normalised/uppercased).

    Returns:
        Final AgentState with all fields populated by the pipeline nodes.

    Raises:
        ValueError: If the ticker is invalid or has no price data available.
        Exception:  If any node raises an unexpected error.
    """
    initial_state: AgentState = {
        "ticker": ticker,
        "news_context": [],
        "sentiment_score": 0.0,
        "volatility_index": 0.0,
        "risk_approved": False,
        "final_memo": "",
        "current_step": "start",
    }

    logger.info("[graph] Starting analysis pipeline for ticker: %s", ticker)

    result = workflow.invoke(initial_state)

    logger.info(
        "[graph] Pipeline complete for %s — step: %s | approved: %s | vol: %.4f",
        ticker,
        result.get("current_step"),
        result.get("risk_approved"),
        result.get("volatility_index", 0.0),
    )

    return result
