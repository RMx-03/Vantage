import logging

from app.models.state import AgentState

logger = logging.getLogger(__name__)


def run_analyst(state: AgentState) -> dict:
    """
    Analyst node — produces a sentiment score from scraped news context.

    Phase 2 stub: returns a hardcoded positive sentiment score so the
    full graph can be tested end-to-end. Replaced with a real Ollama
    HTTP call in Phase 3.

    Args:
        state: Current AgentState (reads 'ticker' and 'news_context')

    Returns:
        Partial state dict with 'sentiment_score' and 'current_step'.
    """
    ticker = state["ticker"]
    news_context = state.get("news_context", [])

    logger.info(
        "[analyst] Analysing sentiment for %s (%d headline(s))",
        ticker,
        len(news_context),
    )

    # TODO(Phase 3): Replace this stub with a real Ollama HTTP call.
    #   from app.prompts.sentiment_prompt import build_sentiment_prompt
    #   from app.core.config import settings
    #   import httpx, json, time
    #
    #   prompt = build_sentiment_prompt(ticker, news_context)
    #   payload = {
    #       "model": settings.OLLAMA_MODEL,
    #       "prompt": prompt,
    #       "stream": False,
    #       "format": "json",
    #   }
    #   with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
    #       resp = client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload)
    #       outer = resp.json()
    #       inner = json.loads(outer["response"])
    #       sentiment_score = max(-1.0, min(1.0, float(inner["sentiment_score"])))

    sentiment_score: float = 0.65  # Stub — moderate positive sentiment

    logger.info(
        "[analyst] Sentiment score for %s: %.2f (stub — Phase 3 pending)",
        ticker,
        sentiment_score,
    )

    return {
        "sentiment_score": sentiment_score,
        "current_step": "analyst_complete",
    }
