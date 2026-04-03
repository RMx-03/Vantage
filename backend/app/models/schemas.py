from typing import List, TypedDict

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# LangGraph Agent State
# Internal state object passed between every node in the agent graph.
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    ticker: str
    news_context: List[str]
    sentiment_score: float  # range: -1.0 to 1.0
    volatility_index: float
    risk_approved: bool
    final_memo: str
    current_step: str


# ---------------------------------------------------------------------------
# FastAPI Request / Response Schemas
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """Request body for POST /api/v1/analyze."""

    ticker: str

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) < 1:
            raise ValueError("ticker must not be empty")
        if len(v) > 10:
            raise ValueError("ticker must be 10 characters or fewer")
        return v

    model_config = {"json_schema_extra": {"examples": [{"ticker": "AAPL"}]}}


class AnalyzeResponse(BaseModel):
    """Response body for POST /api/v1/analyze."""

    ticker: str
    memo: str
    approved: bool

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ticker": "AAPL",
                    "memo": (
                        "[APPROVED] AAPL: Sentiment 0.75, Volatility 18.32%. "
                        "Conditions are favorable for further analysis."
                    ),
                    "approved": True,
                }
            ]
        }
    }
