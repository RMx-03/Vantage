import logging

import numpy as np
import yfinance as yf

from app.core.config import settings
from app.models.state import AgentState

logger = logging.getLogger(__name__)


def run_quant_risk(state: AgentState) -> dict:
    """
    Quant risk node — computes annualised historical volatility and
    applies the risk approval gate.

    Volatility is calculated as the annualised standard deviation of
    daily log returns over the last 30 calendar days (approx. 21 trading days).

    Rejection condition (BOTH must be true):
        volatility_index > settings.VOLATILITY_THRESHOLD
        AND sentiment_score < settings.SENTIMENT_REJECTION_THRESHOLD

    Args:
        state: Current AgentState (reads 'ticker' and 'sentiment_score').

    Returns:
        Partial state dict with 'volatility_index', 'risk_approved',
        'final_memo', and 'current_step'.
    """
    ticker = state["ticker"]
    sentiment_score = state["sentiment_score"]

    logger.info("[quant_risk] Calculating volatility for %s", ticker)

    # ------------------------------------------------------------------
    # Fetch closing prices and compute annualised volatility
    # ------------------------------------------------------------------
    t = yf.Ticker(ticker)
    hist = t.history(period="1mo")
    closes = hist["Close"]

    if len(closes) < 2:
        logger.warning(
            "[quant_risk] Insufficient price data for %s (%d point(s)) — defaulting volatility to 0.0",
            ticker,
            len(closes),
        )
        volatility_index = 0.0
    else:
        log_returns = np.log(closes / closes.shift(1)).dropna()
        daily_std = float(log_returns.std())
        volatility_index = float(daily_std * np.sqrt(252))

    logger.info(
        "[quant_risk] Annualised volatility for %s: %.4f (%.2f%%)",
        ticker,
        volatility_index,
        volatility_index * 100,
    )

    # ------------------------------------------------------------------
    # Risk approval gate — thresholds come from settings / .env
    # ------------------------------------------------------------------
    vol_threshold: float = settings.VOLATILITY_THRESHOLD
    sentiment_threshold: float = settings.SENTIMENT_REJECTION_THRESHOLD

    reject = volatility_index > vol_threshold and sentiment_score < sentiment_threshold

    if reject:
        risk_approved = False
        final_memo = (
            f"[REJECTED] {ticker}: Risk thresholds exceeded. "
            f"Volatility {volatility_index:.2%} is too high given "
            f"low sentiment score of {sentiment_score:.2f}."
        )
    else:
        risk_approved = True
        final_memo = (
            f"[APPROVED] {ticker}: Sentiment {sentiment_score:.2f}, "
            f"Volatility {volatility_index:.2%}. "
            f"Conditions are favorable for further analysis."
        )

    logger.info(
        "[quant_risk] Risk decision for %s: approved=%s (vol=%.4f, sentiment=%.2f)",
        ticker,
        risk_approved,
        volatility_index,
        sentiment_score,
    )

    return {
        "volatility_index": volatility_index,
        "risk_approved": risk_approved,
        "final_memo": final_memo,
        "current_step": "quant_risk_complete",
    }
