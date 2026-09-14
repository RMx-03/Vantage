from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.errors import SafeError, VantageError
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DailyBar,
    DataQuality,
    EvidenceSource,
    MarketSnapshot,
    ModelInfo,
    ModelQuality,
    NewsItem,
    NewsSnapshot,
    OverallQuality,
    Reason,
    ResearchMetric,
    ResearchRun,
    ResearchRunPage,
    ResearchRunRequest,
    ResearchStatus,
    VersionInfo,
    WorkflowStatus,
)


def test_symbol_is_normalized_and_restricted() -> None:
    assert ResearchRunRequest(symbol=" brk.b ").symbol == "BRK.B"
    with pytest.raises(ValidationError):
        ResearchRunRequest(symbol="BTC-USD")


def test_interpretation_rejects_nonfinite_and_out_of_range_score() -> None:
    with pytest.raises(ValidationError):
        AIInterpretation(sentiment_label="positive", sentiment_score=float("nan"), summary="x")
    with pytest.raises(ValidationError):
        AIInterpretation(sentiment_label="positive", sentiment_score=1.01, summary="x")


def test_workflow_values_are_stable() -> None:
    assert [item.value for item in WorkflowStatus] == ["running", "succeeded", "failed"]


def test_research_status_values_are_stable() -> None:
    assert [item.value for item in ResearchStatus] == [
        "informational",
        "review",
        "insufficient_data",
        "failed",
    ]


def test_quality_enums_are_stable() -> None:
    assert [item.value for item in OverallQuality] == ["sufficient", "degraded", "insufficient"]
    assert [item.value for item in ComponentQuality] == [
        "fresh",
        "partial",
        "stale",
        "missing",
        "failed",
    ]
    assert [item.value for item in ModelQuality] == [
        "healthy",
        "degraded",
        "failed",
        "not_run",
    ]


def test_metric_rejects_nonfinite_values() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        ResearchMetric(
            key="return_1_session",
            label="1-Session Return",
            value=float("nan"),
            unit="ratio",
            window_sessions=1,
            as_of=now,
            calculation_version="eod-metrics-v1",
            quality=ComponentQuality.FRESH,
        )


def test_strict_model_rejects_naive_datetime() -> None:
    naive_dt = datetime(2026, 9, 14, 12, 0, 0)
    with pytest.raises(ValidationError):
        DailyBar(
            symbol="AAPL",
            session_date=date(2026, 9, 11),
            open=150.0,
            high=155.0,
            low=149.0,
            close=152.0,
            adjusted_close=152.0,
            volume=1000000,
            currency="USD",
            provider="yfinance",
            retrieved_at=naive_dt,
            adjustment_state="split_and_dividend_adjusted",
        )


def test_strict_model_forbids_extra_fields() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        DailyBar(
            symbol="AAPL",
            session_date=date(2026, 9, 11),
            open=150.0,
            high=155.0,
            low=149.0,
            close=152.0,
            adjusted_close=152.0,
            volume=1000000,
            currency="USD",
            provider="yfinance",
            retrieved_at=now,
            adjustment_state="split_and_dividend_adjusted",
            extra_unwanted_field="bad",  # type: ignore[call-arg]
        )


def test_safe_error_and_vantage_error() -> None:
    err = SafeError(code="INVALID_SYMBOL", message="Symbol is invalid", retryable=False)
    assert err.code == "INVALID_SYMBOL"
    assert not err.retryable

    exc = VantageError(code="TEST_ERR", safe_message="Safe error text", retryable=True, run_id="123")
    assert str(exc) == "Safe error text"
    assert exc.code == "TEST_ERR"
    assert exc.retryable
    assert exc.run_id == "123"
