from typing import List

from pydantic import BaseModel, field_validator

# AgentState now lives in app.models.state — re-exported here for backward compat
from app.models.state import AgentState as AgentState  # noqa: F401

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
