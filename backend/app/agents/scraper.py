import logging
from typing import Any

import yfinance as yf

from app.models.state import AgentState

logger = logging.getLogger(__name__)

_MAX_HEADLINES = 10


def run_scraper(state: AgentState) -> dict:
    """
    Scraper node — fetches market data and news headlines for the given ticker.

    Validates the ticker by confirming price history exists via yfinance, then
    pulls up to 10 recent news headlines. Populates news_context in the state.

    Args:
        state: Current AgentState (must have 'ticker' set).

    Returns:
        Partial state dict updating 'news_context' and 'current_step'.

    Raises:
        ValueError: If the ticker has no price history (invalid or delisted).
    """
    ticker = state["ticker"]
    logger.info("[scraper] Fetching data for ticker: %s", ticker)

    t = yf.Ticker(ticker)

    # ------------------------------------------------------------------
    # Validate ticker — an empty history DataFrame means invalid/delisted
    # ------------------------------------------------------------------
    hist = t.history(period="1mo")
    if hist.empty:
        raise ValueError(
            f"No price data found for ticker '{ticker}'. "
            "It may be invalid, delisted, or unsupported by yfinance."
        )

    logger.info(
        "[scraper] Price history confirmed for %s (%d trading day(s))",
        ticker,
        len(hist),
    )

    # ------------------------------------------------------------------
    # Fetch news headlines — handle both old and new yfinance schemas
    # Old schema: {"title": "...", "publisher": "...", ...}
    # New schema: {"content": {"title": "...", ...}, ...}
    # ------------------------------------------------------------------
    headlines: list[str] = []
    try:
        raw_news: list[Any] = t.news or []
        for item in raw_news[:_MAX_HEADLINES]:
            if not isinstance(item, dict):
                continue
            title: str = item.get("title") or (item.get("content") or {}).get(
                "title", ""
            )
            title = str(title).strip()
            if title:
                headlines.append(title)
    except Exception as exc:
        logger.warning("[scraper] News fetch failed for %s: %s", ticker, exc)

    if not headlines:
        logger.warning(
            "[scraper] No headlines retrieved for %s — using fallback", ticker
        )
        headlines = [f"No recent news found for {ticker}."]

    logger.info("[scraper] Collected %d headline(s) for %s", len(headlines), ticker)

    return {
        "news_context": headlines,
        "current_step": "scraper_complete",
    }
