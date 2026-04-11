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

    from app.prompts.sentiment_prompt import build_sentiment_prompt
    from app.core.config import settings
    import httpx, json, time

    prompt = build_sentiment_prompt(ticker, news_context)
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    
    try:
        with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
            resp = client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload)
            resp.raise_for_status()
            outer = resp.json()
            # Some models may return the stringified JSON or proper object inside response
            # Let's handle both
            response_text = outer.get("response", "{}")
            inner = json.loads(response_text) if isinstance(response_text, str) else response_text
            sentiment_score = max(-1.0, min(1.0, float(inner.get("sentiment_score", 0.0))))
            logger.info("[analyst] Successfully retrieved sentiment from Ollama.")
    except Exception as e:
        logger.error("[analyst] Failed to connect / parse Ollama. Error: %s", e)
        sentiment_score = 0.0 # Default if failed

    logger.info(
        "[analyst] Sentiment score for %s: %.2f",
        ticker,
        sentiment_score,
    )

    return {
        "sentiment_score": sentiment_score,
        "current_step": "analyst_complete",
    }
