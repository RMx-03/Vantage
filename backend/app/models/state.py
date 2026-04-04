from typing import List, TypedDict


class AgentState(TypedDict):
    """
    Shared state object passed between every node in the LangGraph workflow.

    Each agent node receives the full state and returns a partial dict
    containing only the fields it updates. LangGraph merges these partial
    updates into the running state automatically.

    Fields
    ------
    ticker : str
        Normalised (uppercase, stripped) stock ticker symbol, e.g. "AAPL".
    news_context : List[str]
        Recent news headlines scraped for the ticker (max 10).
        Populated by the Scraper node.
    sentiment_score : float
        Market sentiment derived from news context. Range: -1.0 (very
        negative) to 1.0 (very positive). Populated by the Analyst node.
    volatility_index : float
        Annualised historical volatility computed from 30-day daily log
        returns. Populated by the QuantRisk node.
    risk_approved : bool
        True if the ticker passes the risk gate; False if rejected.
        Set by the QuantRisk node.
    final_memo : str
        Human-readable investment memo string, prefixed with [APPROVED]
        or [REJECTED]. Set by the QuantRisk node.
    current_step : str
        Name of the last completed pipeline step. Used for logging and
        debugging. Values: "start" → "scraper_complete" →
        "analyst_complete" → "quant_risk_complete".
    """

    ticker: str
    news_context: List[str]
    sentiment_score: float  # range: -1.0 to 1.0
    volatility_index: float
    risk_approved: bool
    final_memo: str
    current_step: str
