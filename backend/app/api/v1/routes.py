import logging

from fastapi import APIRouter, Depends, HTTPException

from app.agents.graph import run_analysis
from app.api.deps import get_current_user
from app.models.schemas import AnalyzeRequest, AnalyzeResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Run a financial analysis on a stock ticker",
    description=(
        "Accepts a stock ticker symbol and runs it through the Vantage multi-agent "
        "pipeline: **Scraper → Analyst → QuantRisk**. Returns a structured investment "
        "memo and an approval flag indicating whether risk thresholds are met.\n\n"
        "**Phase 2**: Real LangGraph pipeline with live yfinance market data. "
        "Analyst sentiment is stubbed at 0.65 — live LLM inference wired in Phase 3."
    ),
)
def analyze(request: AnalyzeRequest, _user: dict = Depends(get_current_user)) -> AnalyzeResponse:
    """
    Entry point for the Vantage agentic research pipeline.

    Receives a ticker symbol, orchestrates the LangGraph agent workflow
    (Scraper → Analyst → QuantRisk), and returns a structured investment
    memo alongside a binary risk-approval decision.

    Uses a synchronous route handler because the pipeline makes blocking
    yfinance HTTP calls. FastAPI automatically runs sync handlers in a
    thread pool executor, keeping the event loop unblocked.
    """
    logger.info("[analyze] Received ticker: %s", request.ticker)

    try:
        result = run_analysis(request.ticker)
    except ValueError as exc:
        logger.warning("[analyze] Invalid ticker '%s': %s", request.ticker, exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(
            "[analyze] Pipeline failed for '%s': %s",
            request.ticker,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Analysis pipeline failed. Check server logs for details.",
        )

    logger.info(
        "[analyze] Analysis complete for %s: approved=%s, vol=%.4f, sentiment=%.2f",
        request.ticker,
        result["risk_approved"],
        result["volatility_index"],
        result["sentiment_score"],
    )

    return AnalyzeResponse(
        ticker=result["ticker"],
        memo=result["final_memo"],
        approved=result["risk_approved"],
    )
