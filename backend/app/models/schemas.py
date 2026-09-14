from pydantic import BaseModel, field_validator

from app.domain.research import ResearchRun, ResearchRunPage, ResearchRunRequest


class AnalyzeRequest(BaseModel):
    """Deprecated request body for POST /api/v1/analyze."""

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


__all__ = [
    "AnalyzeRequest",
    "ResearchRun",
    "ResearchRunPage",
    "ResearchRunRequest",
]
