import logging

from fastapi import APIRouter

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
        "> **Phase 1 stub** — returns a placeholder response. "
        "Full agent graph is wired in Phase 2."
    ),
)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Entry point for the Vantage agentic research pipeline.

    Receives a ticker symbol, orchestrates the LangGraph agent workflow
    (Scraper → Analyst → QuantRisk), and returns a structured investment
    memo alongside a binary risk-approval decision.

    Phase 1: Returns a deterministic stub response so the API contract
    is immediately testable end-to-end before agent logic is wired in.
    """
    logger.info("[analyze] Received ticker: %s", request.ticker)

    # TODO(Phase 2): Replace this stub with a real LangGraph pipeline call.
    #   from app.agents.graph import run_analysis
    #   result = run_analysis(request.ticker)
    #   return AnalyzeResponse(
    #       ticker=result["ticker"],
    #       memo=result["final_memo"],
    #       approved=result["risk_approved"],
    #   )

    return AnalyzeResponse(
        ticker=request.ticker,
        memo=f"[STUB] Analysis for {request.ticker} is pending agent implementation.",
        approved=False,
    )
