from datetime import UTC, date, datetime, timedelta
import pytest

from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DailyBar,
    FilingsSnapshot,
    FundamentalsSnapshot,
    MacroObservation,
    MacroSnapshot,
    MarketSnapshot,
    ModelQuality,
    NewsItem,
    NewsSnapshot,
    OverallQuality,
    PriceCrossCheckSnapshot,
    Reason,
    ResearchMetric,
    ResearchStatus,
    RoleQuality,
)
from app.services.policy import (
    REASON_ORDER,
    PolicyResult,
    apply_policy,
    assess_quality,
    order_reasons,
)
from app.services.run_inputs import RunInputs


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
    stale_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    result = apply_policy(stale_market, healthy_news, healthy_model, metrics=[])
    assert result.research_status == ResearchStatus.INSUFFICIENT_DATA
    assert result.data_quality.overall == OverallQuality.INSUFFICIENT
    assert result.reasons[0].code == "STALE_PRICE_DATA"
    assert result.reasons[0].severity == "blocking"


def test_bar_after_latest_completed_session_is_blocking(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    future_market = valid_market.model_copy(
        update={
            "latest_completed_session": valid_market.bars[-1].session_date
            - timedelta(days=1)
        }
    )
    result = apply_policy(future_market, healthy_news, healthy_model, metrics=[])
    assert result.research_status == ResearchStatus.INSUFFICIENT_DATA
    assert result.data_quality.prices == ComponentQuality.STALE
    assert "STALE_PRICE_DATA" in [reason.code for reason in result.reasons]


def test_model_not_run_is_not_reported_as_model_failure(
    stale_market: MarketSnapshot, healthy_news: NewsSnapshot
) -> None:
    interpretation = AIInterpretation(
        sentiment_label="unavailable",
        summary="Automated interpretation was not run because price data was inadequate.",
        abstained=True,
        abstention_reason="MODEL_NOT_RUN",
    )
    result = apply_policy(stale_market, healthy_news, interpretation, metrics=[])
    assert result.data_quality.model == ModelQuality.NOT_RUN
    assert "MODEL_UNAVAILABLE" not in [reason.code for reason in result.reasons]
    assert "MODEL_OUTPUT_INVALID" not in [reason.code for reason in result.reasons]


def test_invalid_price_series_has_one_specific_blocking_reason(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
) -> None:
    invalid_market = valid_market.model_copy(
        update={
            "quality": ComponentQuality.FAILED,
            "error_code": "INVALID_PRICE_SERIES",
        }
    )
    interpretation = AIInterpretation(
        sentiment_label="unavailable",
        summary="Automated interpretation was not run because price data was invalid.",
        abstained=True,
        abstention_reason="MODEL_NOT_RUN",
    )
    result = apply_policy(invalid_market, healthy_news, interpretation, metrics=[])
    blocking_codes = [
        reason.code for reason in result.reasons if reason.severity == "blocking"
    ]
    assert blocking_codes == ["INVALID_PRICE_SERIES"]


def test_market_provider_failure_has_one_explicit_blocking_reason(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    failed_market = valid_market.model_copy(
        update={
            "quality": ComponentQuality.FAILED,
            "error_code": "MARKET_DATA_PROVIDER_FAILED",
        }
    )

    result = apply_policy(failed_market, healthy_news, healthy_model, metrics=[])

    assert result.research_status == ResearchStatus.INSUFFICIENT_DATA
    assert _codes(result, "blocking") == ["MARKET_DATA_PROVIDER_FAILED"]
    assert _codes(result, "warning") == []


def test_news_provider_failure_is_an_explicit_degraded_warning(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    failed_news = healthy_news.model_copy(
        update={
            "quality": ComponentQuality.FAILED,
            "error_code": "NEWS_PROVIDER_FAILED",
        }
    )

    result = apply_policy(valid_market, failed_news, healthy_model, metrics=[])

    assert result.research_status == ResearchStatus.REVIEW
    assert result.data_quality.news == ComponentQuality.FAILED
    assert _codes(result, "warning") == ["NEWS_PROVIDER_FAILED"]
    assert _codes(result, "blocking") == []


def test_partial_news_is_an_explicit_degraded_warning(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    partial_news = healthy_news.model_copy(update={"quality": ComponentQuality.PARTIAL})

    result = apply_policy(valid_market, partial_news, healthy_model, metrics=[])

    assert result.research_status == ResearchStatus.REVIEW
    assert result.data_quality.news == ComponentQuality.PARTIAL
    assert _codes(result, "warning") == ["PARTIAL_NEWS_COVERAGE"]
    assert _codes(result, "blocking") == []


def test_stale_news_degrades_overall_quality(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    stale_news = healthy_news.model_copy(update={"quality": ComponentQuality.STALE})

    result = apply_policy(valid_market, stale_news, healthy_model, metrics=[])

    assert result.research_status == ResearchStatus.REVIEW
    assert result.data_quality.news == ComponentQuality.STALE
    assert result.data_quality.overall == OverallQuality.DEGRADED


def test_model_warning_degrades_quality_without_discarding_interpretation(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    warned_model = healthy_model.model_copy(
        update={"warnings": ["Interpretation confidence is limited."]}
    )

    result = apply_policy(valid_market, healthy_news, warned_model, metrics=[])

    assert result.research_status == ResearchStatus.REVIEW
    assert result.data_quality.model == ModelQuality.DEGRADED
    assert result.warnings == ["Interpretation confidence is limited."]


def test_healthy_run_is_informational(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    result = apply_policy(valid_market, healthy_news, healthy_model, metrics=[])
    assert result.research_status == ResearchStatus.INFORMATIONAL
    assert result.data_quality.overall == OverallQuality.SUFFICIENT
    assert result.data_quality.prices == ComponentQuality.FRESH
    assert result.data_quality.news == ComponentQuality.FRESH
    assert result.data_quality.model == ModelQuality.HEALTHY


@pytest.mark.parametrize(
    "provider_quality",
    [
        ComponentQuality.PARTIAL,
        ComponentQuality.STALE,
        ComponentQuality.MISSING,
        ComponentQuality.FAILED,
    ],
)
def test_market_provider_quality_is_never_upgraded(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
    provider_quality: ComponentQuality,
) -> None:
    market = valid_market.model_copy(update={"quality": provider_quality})

    quality = assess_quality(market, healthy_news, healthy_model)

    assert quality.prices == provider_quality
    assert quality.overall == (
        OverallQuality.DEGRADED
        if provider_quality == ComponentQuality.PARTIAL
        else OverallQuality.INSUFFICIENT
    )


def test_elevated_volatility_triggers_review(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
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
    result = apply_policy(
        valid_market, healthy_news, healthy_model, metrics=[high_vol_metric]
    )
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


def test_reason_ordering_places_blocking_before_warning_and_follows_registry_index() -> (
    None
):
    reasons = [
        Reason(
            code="ELEVATED_VOLATILITY",
            label="Elevated Volatility",
            severity="warning",
            description="d",
        ),
        Reason(
            code="STALE_PRICE_DATA",
            label="Stale Price Data",
            severity="blocking",
            description="d",
        ),
        Reason(
            code="MODEL_OUTPUT_INVALID",
            label="Model Output Invalid",
            severity="warning",
            description="d",
        ),
        Reason(
            code="MARKET_DATA_PROVIDER_FAILED",
            label="Market Provider Failed",
            severity="blocking",
            description="d",
        ),
    ]
    ordered = order_reasons(reasons)
    assert [r.code for r in ordered] == [
        "MARKET_DATA_PROVIDER_FAILED",
        "STALE_PRICE_DATA",
        "MODEL_OUTPUT_INVALID",
        "ELEVATED_VOLATILITY",
    ]


# ---- policy v2: quality and reasons for the optional data roles ----

_NOW = datetime(2026, 9, 11, 20, 0, tzinfo=UTC)


def _ctx(market: MarketSnapshot) -> MarketSnapshot:
    return market.model_copy(
        update={"context_bars": {"SPY": market.bars, "XLK": market.bars}}
    )


def _filings(**kw: object) -> FilingsSnapshot:
    base: dict[str, object] = {
        "symbol": "AAPL",
        "items": [],
        "provider": "sec",
        "retrieved_at": _NOW,
        "quality": ComponentQuality.FRESH,
        "sic_code": "3571",
    }
    base.update(kw)
    return FilingsSnapshot(**base)  # type: ignore[arg-type]


def _funds(**kw: object) -> FundamentalsSnapshot:
    base: dict[str, object] = {
        "symbol": "AAPL",
        "provider": "sec",
        "retrieved_at": _NOW,
        "quality": ComponentQuality.FRESH,
    }
    base.update(kw)
    return FundamentalsSnapshot(**base)  # type: ignore[arg-type]


def _macro(**kw: object) -> MacroSnapshot:
    base: dict[str, object] = {
        "provider": "fred",
        "retrieved_at": _NOW,
        "quality": ComponentQuality.FRESH,
    }
    base.update(kw)
    return MacroSnapshot(**base)  # type: ignore[arg-type]


def _crosscheck(**kw: object) -> PriceCrossCheckSnapshot:
    base: dict[str, object] = {
        "symbol": "AAPL",
        "provider": "tiingo",
        "retrieved_at": _NOW,
        "quality": ComponentQuality.FRESH,
    }
    base.update(kw)
    return PriceCrossCheckSnapshot(**base)  # type: ignore[arg-type]


def _configured(**kw: object) -> RunInputs:
    base: dict[str, object] = {
        "filings": _filings(),
        "fundamentals": _funds(),
        "macro": _macro(),
        "crosscheck": _crosscheck(),
        "sector_etf": "XLK",
        "not_configured": frozenset(),
    }
    base.update(kw)
    return RunInputs(**base)  # type: ignore[arg-type]


def _deviation(value: float) -> ResearchMetric:
    return ResearchMetric(
        key="price_crosscheck_max_deviation",
        label="gap",
        value=value,
        unit="ratio",
        window_sessions=None,
        as_of=_NOW,
        calculation_version="eod-metrics-v3",
        quality=ComponentQuality.FRESH,
    )


def _run(
    market: MarketSnapshot,
    news: NewsSnapshot,
    model: AIInterpretation,
    inputs: RunInputs,
    metrics: list[ResearchMetric] | None = None,
) -> PolicyResult:
    return apply_policy(_ctx(market), news, model, metrics or [], inputs)


def _codes(result: PolicyResult, severity: str) -> list[str]:
    return [r.code for r in result.reasons if r.severity == severity]


def test_every_role_not_configured_gives_four_info_reasons(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    result = _run(valid_market, healthy_news, healthy_model, RunInputs())
    not_configured = [r for r in result.reasons if r.code == "PROVIDER_NOT_CONFIGURED"]
    assert len(not_configured) == 4
    assert all(r.severity == "info" and r.metric_keys for r in not_configured)
    assert all(r.policy_version == "research-policy-v2" for r in result.reasons)
    assert result.data_quality.filings == RoleQuality.NOT_CONFIGURED
    assert result.data_quality.crosscheck == RoleQuality.NOT_CONFIGURED
    assert result.data_quality.overall == OverallQuality.SUFFICIENT
    assert result.research_status == ResearchStatus.INFORMATIONAL


def test_edgar_failure_is_one_warning_and_review(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    inputs = _configured(
        filings=None,
        fundamentals=None,
        failed={
            "filings": "SEC_PROVIDER_FAILED",
            "fundamentals": "SEC_PROVIDER_FAILED",
        },
    )
    result = _run(valid_market, healthy_news, healthy_model, inputs)
    assert result.data_quality.filings == RoleQuality.FAILED
    assert result.data_quality.fundamentals == RoleQuality.FAILED
    assert _codes(result, "warning") == ["FILINGS_PROVIDER_FAILED"]
    assert result.data_quality.overall == OverallQuality.DEGRADED
    assert result.research_status == ResearchStatus.REVIEW
    assert "SECTOR_UNMAPPED" not in _codes(result, "info")


@pytest.mark.parametrize(
    ("inputs", "code"),
    [
        (
            _configured(
                filings=_filings(
                    quality=ComponentQuality.MISSING, error_code="NO_SEC_FILER_RECORD"
                )
            ),
            "NO_SEC_FILER_RECORD",
        ),
        (_configured(sector_etf=None), "SECTOR_UNMAPPED"),
        (
            _configured(
                fundamentals=_funds(
                    quality=ComponentQuality.MISSING,
                    error_code="FUNDAMENTALS_UNAVAILABLE",
                )
            ),
            "FUNDAMENTALS_UNAVAILABLE",
        ),
        (
            _configured(
                macro=_macro(
                    observations=[
                        MacroObservation(
                            series_id="DGS10",
                            value=4.0,
                            observation_date=date(2026, 8, 1),
                            quality=ComponentQuality.STALE,
                        )
                    ]
                )
            ),
            "MACRO_DATA_STALE",
        ),
        (
            _configured(macro=None, failed={"macro": "MACRO_PROVIDER_FAILED"}),
            "MACRO_PROVIDER_FAILED",
        ),
        (
            _configured(crosscheck=_crosscheck(quality=ComponentQuality.MISSING)),
            "PRICE_CROSSCHECK_UNAVAILABLE",
        ),
    ],
)
def test_expected_gaps_are_info_only(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
    inputs: RunInputs,
    code: str,
) -> None:
    result = _run(valid_market, healthy_news, healthy_model, inputs)
    assert code in _codes(result, "info")
    assert _codes(result, "warning") == []
    assert result.research_status == ResearchStatus.INFORMATIONAL


def test_sector_unmapped_needs_a_sic_code(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    inputs = _configured(sector_etf=None, filings=_filings(sic_code=None))
    result = _run(valid_market, healthy_news, healthy_model, inputs)
    assert "SECTOR_UNMAPPED" not in [r.code for r in result.reasons]


def test_crosscheck_gap_of_1_2_percent_is_a_warning(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    result = _run(
        valid_market,
        healthy_news,
        healthy_model,
        _configured(),
        [_deviation(0.012)],
    )
    reason = next(r for r in result.reasons if r.code == "PRICE_SOURCES_DISAGREE")
    assert reason.severity == "warning"
    assert reason.threshold == 0.01
    assert result.research_status == ResearchStatus.REVIEW


def test_crosscheck_gap_of_exactly_1_percent_has_no_reason(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    result = _run(
        valid_market, healthy_news, healthy_model, _configured(), [_deviation(0.01)]
    )
    assert "PRICE_SOURCES_DISAGREE" not in [r.code for r in result.reasons]
    assert result.research_status == ResearchStatus.INFORMATIONAL


def test_missing_context_bars_with_usable_market_is_one_info_reason(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    result = apply_policy(valid_market, healthy_news, healthy_model, [], _configured())
    matches = [r for r in result.reasons if r.code == "CONTEXT_BARS_UNAVAILABLE"]
    assert len(matches) == 1
    assert matches[0].severity == "info"
    assert result.research_status == ResearchStatus.INFORMATIONAL


def test_context_bars_reason_absent_when_market_is_not_usable(
    stale_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    result = apply_policy(stale_market, healthy_news, healthy_model, [], RunInputs())
    assert "CONTEXT_BARS_UNAVAILABLE" not in [r.code for r in result.reasons]


def test_v2_reasons_are_ordered_by_severity_then_registry(
    valid_market: MarketSnapshot,
    healthy_news: NewsSnapshot,
    healthy_model: AIInterpretation,
) -> None:
    inputs = _configured(
        filings=None,
        fundamentals=None,
        macro=None,
        failed={"filings": "X", "fundamentals": "X", "macro": "X"},
    )
    result = apply_policy(
        valid_market,
        healthy_news.model_copy(update={"quality": ComponentQuality.PARTIAL}),
        healthy_model,
        [_deviation(0.02)],
        inputs,
    )
    sev = {"blocking": 0, "warning": 1, "info": 2}
    keys = [(sev[r.severity], REASON_ORDER[r.code]) for r in result.reasons]
    assert keys == sorted(keys)
    codes = [r.code for r in result.reasons]
    assert codes.index("PARTIAL_NEWS_COVERAGE") < codes.index("FILINGS_PROVIDER_FAILED")
    assert codes.index("FILINGS_PROVIDER_FAILED") < codes.index("MACRO_PROVIDER_FAILED")
    assert (
        REASON_ORDER["MODEL_OUTPUT_INVALID"] < REASON_ORDER["PROVIDER_NOT_CONFIGURED"]
    )
    assert (
        REASON_ORDER["CONTEXT_BARS_UNAVAILABLE"] < REASON_ORDER["ELEVATED_VOLATILITY"]
    )
