from datetime import UTC, date, datetime, timedelta
import pytest

from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DailyBar,
    MarketSnapshot,
    ModelQuality,
    NewsItem,
    NewsSnapshot,
    OverallQuality,
    Reason,
    ResearchMetric,
    ResearchStatus,
)
from app.services.policy import (
    REASON_ORDER,
    PolicyResult,
    apply_policy,
    assess_quality,
    order_reasons,
)


@pytest.fixture
def valid_market() -> MarketSnapshot:
    session = date(2026, 9, 11)
    bars = [
        DailyBar(
            symbol="AAPL",
            session_date=session - timedelta(days=21 - i),
            open=150.0,
            high=155.0,
            low=149.0,
            close=152.0,
            adjusted_close=152.0,
            volume=1_000_000,
            currency="USD",
            provider="fixture",
            retrieved_at=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
            adjustment_state="split_adjusted",
        )
        for i in range(21)
    ]
    return MarketSnapshot(
        symbol="AAPL",
        bars=bars,
        provider="fixture",
        retrieved_at=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
        as_of=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
        latest_completed_session=bars[-1].session_date,
        content_hash="a" * 64,
        quality=ComponentQuality.FRESH,
    )


@pytest.fixture
def stale_market(valid_market: MarketSnapshot) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="AAPL",
        bars=valid_market.bars[:-1],
        provider="fixture",
        retrieved_at=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
        as_of=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
        latest_completed_session=valid_market.bars[-1].session_date,
        content_hash="a" * 64,
        quality=ComponentQuality.STALE,
    )


@pytest.fixture
def missing_news() -> NewsSnapshot:
    return NewsSnapshot(
        symbol="AAPL",
        items=[],
        provider="fixture",
        retrieved_at=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
        quality=ComponentQuality.MISSING,
    )


@pytest.fixture
def healthy_news() -> NewsSnapshot:
    items = [
        NewsItem(
            evidence_id="news-1",
            provider="fixture",
            publisher="Reuters",
            title="Apple announces new product line",
            url="https://example.com/news1",
            event_time=datetime(2026, 9, 11, 15, 0, tzinfo=UTC),
            retrieved_at=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
            content_hash="b" * 64,
        ),
        NewsItem(
            evidence_id="news-2",
            provider="fixture",
            publisher="Bloomberg",
            title="Supply chain checks positive for tech",
            url="https://example.com/news2",
            event_time=datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
            retrieved_at=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
            content_hash="c" * 64,
        ),
    ]
    return NewsSnapshot(
        symbol="AAPL",
        items=items,
        provider="fixture",
        retrieved_at=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
        coverage_start=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
        coverage_end=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
        quality=ComponentQuality.FRESH,
    )


@pytest.fixture
def healthy_model() -> AIInterpretation:
    return AIInterpretation(
        sentiment_label="positive",
        sentiment_score=0.45,
        summary="Recent news reflects solid demand and operational execution.",
        evidence_ids=["news-1", "news-2"],
        warnings=[],
        abstained=False,
    )


def model_failure(code: str = "MODEL_OUTPUT_INVALID") -> AIInterpretation:
    return AIInterpretation(
        sentiment_label="unavailable",
        sentiment_score=None,
        summary="Automated interpretation was unavailable for this research session.",
        evidence_ids=[],
        warnings=["Model interpretation failed: " + code],
        abstained=True,
        abstention_reason=code,
    )


def test_model_failure_is_review_not_neutral(
    valid_market: MarketSnapshot, missing_news: NewsSnapshot
) -> None:
    result = apply_policy(
        valid_market,
        missing_news,
        model_failure("MODEL_OUTPUT_INVALID"),
        metrics=[],
    )
    assert result.research_status == ResearchStatus.REVIEW
    assert result.data_quality.model == ModelQuality.FAILED
    assert "MODEL_OUTPUT_INVALID" in [r.code for r in result.reasons]
    assert result.interpretation.sentiment_score is None


def test_stale_prices_are_blocking(
    stale_market: MarketSnapshot, healthy_news: NewsSnapshot, healthy_model: AIInterpretation
) -> None:
    result = apply_policy(stale_market, healthy_news, healthy_model, metrics=[])
    assert result.research_status == ResearchStatus.INSUFFICIENT_DATA
    assert result.data_quality.overall == OverallQuality.INSUFFICIENT
    assert result.reasons[0].code == "STALE_PRICE_DATA"
    assert result.reasons[0].severity == "blocking"


def test_healthy_run_is_informational(
    valid_market: MarketSnapshot, healthy_news: NewsSnapshot, healthy_model: AIInterpretation
) -> None:
    result = apply_policy(valid_market, healthy_news, healthy_model, metrics=[])
    assert result.research_status == ResearchStatus.INFORMATIONAL
    assert result.data_quality.overall == OverallQuality.SUFFICIENT
    assert result.data_quality.prices == ComponentQuality.FRESH
    assert result.data_quality.news == ComponentQuality.FRESH
    assert result.data_quality.model == ModelQuality.HEALTHY


def test_elevated_volatility_triggers_review(
    valid_market: MarketSnapshot, healthy_news: NewsSnapshot, healthy_model: AIInterpretation
) -> None:
    high_vol_metric = ResearchMetric(
        key="annualized_volatility_20",
        label="20-session annualized volatility",
        value=0.55,
        unit="ratio",
        window_sessions=20,
        as_of=datetime(2026, 9, 11, 20, 0, tzinfo=UTC),
        calculation_version="eod-metrics-v1",
        quality=ComponentQuality.FRESH,
    )
    result = apply_policy(valid_market, healthy_news, healthy_model, metrics=[high_vol_metric])
    assert result.research_status == ResearchStatus.REVIEW
    assert "ELEVATED_VOLATILITY" in [r.code for r in result.reasons]


def test_negative_sentiment_triggers_review(
    valid_market: MarketSnapshot, healthy_news: NewsSnapshot
) -> None:
    negative_model = AIInterpretation(
        sentiment_label="negative",
        sentiment_score=-0.65,
        summary="Headlines reflect severe regulatory and litigation headwinds.",
        evidence_ids=["news-1"],
        warnings=[],
        abstained=False,
    )
    result = apply_policy(valid_market, healthy_news, negative_model, metrics=[])
    assert result.research_status == ResearchStatus.REVIEW
    assert "NEGATIVE_NEWS_SENTIMENT" in [r.code for r in result.reasons]


def test_reason_ordering_places_blocking_before_warning_and_follows_registry_index() -> None:
    reasons = [
        Reason(code="ELEVATED_VOLATILITY", label="Elevated Volatility", severity="warning", description="d"),
        Reason(code="STALE_PRICE_DATA", label="Stale Price Data", severity="blocking", description="d"),
        Reason(code="MODEL_OUTPUT_INVALID", label="Model Output Invalid", severity="warning", description="d"),
        Reason(code="MARKET_DATA_PROVIDER_FAILED", label="Market Provider Failed", severity="blocking", description="d"),
    ]
    ordered = order_reasons(reasons)
    assert [r.code for r in ordered] == [
        "MARKET_DATA_PROVIDER_FAILED",
        "STALE_PRICE_DATA",
        "MODEL_OUTPUT_INVALID",
        "ELEVATED_VOLATILITY",
    ]
