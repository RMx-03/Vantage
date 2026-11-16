import pytest

from app.services.research_run import get_research_service


def test_get_research_service_reuses_the_stateless_instance() -> None:
    clear = getattr(get_research_service, "cache_clear", None)
    if clear is not None:
        clear()
    try:
        first = get_research_service()
        second = get_research_service()
        assert second is first
    finally:
        clear = getattr(get_research_service, "cache_clear", None)
        if clear is not None:
            clear()


def _service_with(providers, **kwargs):
    from unittest.mock import MagicMock

    from app.repositories.research_runs import (
        ResearchRunRepository,
        RunningResearchRun,
    )
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.services.research_run import ResearchRunService

    now = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
    repo = MagicMock(spec=ResearchRunRepository)
    repo.create_running.return_value = RunningResearchRun(
        id=1,
        public_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        workflow_status="running",
        created_at=now,
        started_at=now,
    )
    return ResearchRunService(repo=repo, providers=providers, **kwargs), repo, now


def _provider_set(market, news):
    from app.providers.llm import DisabledInterpretationProvider
    from app.providers.registry import ProviderSet

    return ProviderSet(
        market=market,
        news=(news,),
        filings=None,
        fundamentals=None,
        macro=None,
        crosscheck=None,
        llm=DisabledInterpretationProvider(),
        not_configured=("filings", "fundamentals", "macro", "crosscheck"),
    )


def test_unconfigured_market_fails_the_run() -> None:
    import pytest
    from uuid import uuid4

    from app.domain.errors import VantageError

    service, repo, now = _service_with(_provider_set(None, object()))

    with pytest.raises(VantageError) as exc:
        service.create(user_id=uuid4(), symbol="AAPL", now=now)

    assert exc.value.code == "MARKET_DATA_PROVIDER_FAILED"
    assert repo.finalize_failure.call_args.kwargs["error_code"] == (
        "MARKET_DATA_PROVIDER_FAILED"
    )


def test_explicit_providers_override_the_set() -> None:
    from unittest.mock import MagicMock

    market, news = MagicMock(), MagicMock()
    service, _, _ = _service_with(
        _provider_set(MagicMock(), MagicMock()),
        market_provider=market,
        news_provider=news,
    )
    assert service.market is market
    assert service.news is news


def test_service_builds_with_no_news_provider() -> None:
    from unittest.mock import MagicMock

    empty = _provider_set(MagicMock(), MagicMock())
    from dataclasses import replace

    service, _, _ = _service_with(replace(empty, news=()))
    assert service.news is None


def test_run_without_news_provider_records_news_failed() -> None:
    from dataclasses import replace
    from unittest.mock import MagicMock
    from uuid import uuid4

    import pytest

    from app.domain.research import ComponentQuality, MarketSnapshot

    market = MagicMock()
    market.name = "stub"

    def fetch(symbol, start, end, now, **kwargs):
        return MarketSnapshot(
            symbol=symbol,
            bars=[],
            provider="stub",
            retrieved_at=now,
            as_of=now,
            latest_completed_session=end,
            content_hash="0" * 64,
            quality=ComponentQuality.FAILED,
            error_code="INVALID_PRICE_SERIES",
        )

    market.fetch_daily_snapshot.side_effect = fetch
    base = _provider_set(market, MagicMock())
    service, repo, now = _service_with(replace(base, news=()))
    repo.save_snapshot.side_effect = RuntimeError("stop after snapshot")

    with pytest.raises(Exception):
        service.create(user_id=uuid4(), symbol="AAPL", now=now)

    news = repo.save_snapshot.call_args.args[3]
    assert news.provider == "none"
    assert news.quality == ComponentQuality.FAILED
    assert news.error_code == "NEWS_PROVIDER_FAILED"
    assert news.items == []


def _market_stub():
    from unittest.mock import MagicMock

    from app.domain.research import ComponentQuality, MarketSnapshot

    market = MagicMock()
    market.name = "stub"

    def fetch(symbol, start, end, now, **kwargs):
        return MarketSnapshot(
            symbol=symbol,
            bars=[],
            provider="stub",
            retrieved_at=now,
            as_of=now,
            latest_completed_session=end,
            content_hash="0" * 64,
            quality=ComponentQuality.FAILED,
            error_code="INVALID_PRICE_SERIES",
        )

    market.fetch_daily_snapshot.side_effect = fetch
    return market


class _StubNews:
    def __init__(self, name, items=None, raises=None):
        self.name = name
        self._items = items or []
        self._raises = raises

    def fetch_company_news(self, symbol, cutoff, now, lookback_days, limit):
        from app.domain.research import ComponentQuality, NewsSnapshot

        if self._raises is not None:
            raise self._raises
        return NewsSnapshot(
            symbol=symbol,
            items=self._items,
            provider=self.name,
            retrieved_at=now,
            quality=(
                ComponentQuality.FRESH if self._items else ComponentQuality.MISSING
            ),
        )


def _news_item(provider, title):
    from datetime import UTC, datetime

    from app.domain.research import EvidenceDetails, NewsItem

    return NewsItem(
        evidence_id=f"{provider}-{title}",
        provider=provider,
        title=title,
        url="https://x.com/story",
        event_time=datetime(2026, 11, 13, 12, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 11, 13, 22, 0, tzinfo=UTC),
        content_hash="b" * 64,
        details=EvidenceDetails(providers=[provider]),
    )


def _run(news_providers):
    from dataclasses import replace
    from uuid import uuid4

    from app.services.snapshots import combined_snapshot_hash

    base = _provider_set(_market_stub(), object())
    service, repo, now = _service_with(replace(base, news=tuple(news_providers)))
    repo.save_snapshot.side_effect = lambda _id, _uid, market, news, *a, **k: (
        combined_snapshot_hash(market, news)
    )
    service.create(user_id=uuid4(), symbol="AAPL", now=now)
    return service, repo


def test_two_providers_one_failing_persists_partial_news() -> None:
    from app.domain.errors import VantageError
    from app.domain.research import ComponentQuality

    failing = _StubNews(
        "alpaca",
        raises=VantageError(code="NEWS_PROVIDER_FAILED", safe_message="down"),
    )
    ok = _StubNews("finnhub", items=[_news_item("finnhub", "Story")])
    service, repo = _run([failing, ok])

    news = repo.save_snapshot.call_args.args[3]
    assert news.provider == "alpaca,finnhub"
    assert news.quality == ComponentQuality.PARTIAL
    assert news.error_code is None
    assert len(news.items) == 1
    records = repo.save_snapshot.call_args.kwargs["providers"]
    news_record = next(r for r in records if r.role == "news")
    assert news_record.provider == "alpaca,finnhub"
    assert news_record.error_code is None
    assert [p.name for p in service.news_providers] == ["alpaca", "finnhub"]
    reasons = [r.code for r in repo.finalize_success.call_args.kwargs["reasons"]]
    assert "PARTIAL_NEWS_COVERAGE" in reasons
    assert "NEWS_PROVIDER_FAILED" not in reasons
    data_quality = repo.finalize_success.call_args.kwargs["data_quality"]
    assert data_quality.news == ComponentQuality.PARTIAL


def test_all_providers_failing_persists_failed_news() -> None:
    from app.domain.errors import VantageError
    from app.domain.research import ComponentQuality

    a = _StubNews("alpaca", raises=VantageError(code="X_FAIL", safe_message="down"))
    f = _StubNews("finnhub", raises=VantageError(code="Y_FAIL", safe_message="down"))
    _, repo = _run([a, f])

    news = repo.save_snapshot.call_args.args[3]
    assert news.quality == ComponentQuality.FAILED
    assert news.error_code == "NEWS_PROVIDER_FAILED"
    assert news.provider == "alpaca,finnhub"
    reasons = [r.code for r in repo.finalize_success.call_args.kwargs["reasons"]]
    assert "NEWS_PROVIDER_FAILED" in reasons


def test_non_vantage_error_becomes_a_failed_snapshot_not_a_failed_run() -> None:
    from app.domain.research import ComponentQuality

    boom = _StubNews("alpaca", raises=RuntimeError("boom"))
    _, repo = _run([boom])

    news = repo.save_snapshot.call_args.args[3]
    assert news.quality == ComponentQuality.FAILED
    assert news.error_code == "NEWS_PROVIDER_FAILED"
    assert news.provider == "alpaca"
    repo.finalize_failure.assert_not_called()
    repo.finalize_success.assert_called_once()


def test_single_provider_snapshot_is_saved_unchanged_with_same_hash() -> None:
    from dataclasses import replace
    from uuid import uuid4

    from app.services.evidence import merge_news
    from app.services.snapshots import combined_snapshot_hash

    only = _StubNews("yfinance", items=[_news_item("yfinance", "Story")])
    returned = {}
    original = only.fetch_company_news

    def spy(*args, **kwargs):
        returned["snap"] = original(*args, **kwargs)
        return returned["snap"]

    only.fetch_company_news = spy  # type: ignore[method-assign]
    base = _provider_set(_market_stub(), object())
    service, repo, now = _service_with(replace(base, news=(only,)))
    repo.save_snapshot.side_effect = lambda _id, _uid, market, news, *a, **k: (
        combined_snapshot_hash(market, news)
    )
    service.create(user_id=uuid4(), symbol="AAPL", now=now)

    market, news = repo.save_snapshot.call_args.args[2:4]
    assert news is returned["snap"]
    assert merge_news([news], symbol="AAPL", limit=10) is news
    assert repo.save_snapshot.side_effect(1, None, market, news) == (
        combined_snapshot_hash(market, returned["snap"])
    )


def test_provider_request_spans_carry_role_and_provider_name(monkeypatch) -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from app.services import data_stage, research_run
    from app.telemetry.redaction import RedactingSpanProcessor

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(research_run, "get_tracer", lambda: tracer)
    monkeypatch.setattr(data_stage, "get_tracer", lambda: tracer)

    _run([_StubNews("alpaca"), _StubNews("finnhub")])

    spans = [s for s in exporter.get_finished_spans() if s.name == "provider_request"]
    pairs = [
        (s.attributes["vantage.provider.role"], s.attributes["vantage.provider.name"])
        for s in spans
    ]
    # The roles run concurrently, so span order is not fixed.
    assert sorted(pairs) == [
        ("market", "stub"),
        ("news", "alpaca"),
        ("news", "finnhub"),
    ]


def test_no_news_provider_opens_no_tagged_news_span(monkeypatch) -> None:
    from dataclasses import replace
    from uuid import uuid4

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from app.domain.errors import VantageError
    from app.services import data_stage, research_run
    from app.telemetry.redaction import RedactingSpanProcessor

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(research_run, "get_tracer", lambda: tracer)
    monkeypatch.setattr(data_stage, "get_tracer", lambda: tracer)

    base = _provider_set(_market_stub(), object())
    service, repo, now = _service_with(replace(base, news=()))
    repo.save_snapshot.side_effect = RuntimeError("stop after snapshot")
    with pytest.raises(VantageError):  # the service wraps the repository error
        service.create(user_id=uuid4(), symbol="AAPL", now=now)

    # With no news provider the service still opens one provider_request span for the
    # empty news snapshot, and it carries no role or name attribute.
    roles = [
        s.attributes.get("vantage.provider.role")
        for s in exporter.get_finished_spans()
        if s.name == "provider_request"
    ]
    assert roles == ["market", None]


# --- Data stage wiring, v3 outputs ------------------------------------------------


class _StubLLM:
    name = "stub-llm"
    model = "stub-model"
    enabled = True

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def interpret(self, *, symbol, metrics, evidence):
        from app.domain.research import AIInterpretation

        self.calls.append({"symbol": symbol, "metrics": metrics, "evidence": evidence})
        filing = next((e for e in evidence if e.source_type == "filing"), evidence[0])
        return AIInterpretation(
            sentiment_label="neutral",
            summary="Filings describe the company's own disclosures.",
            evidence_ids=[filing.evidence_id],
            attribution="company",
        )


def _full_set(*, news=(), filings="fixture", llm=None, **overrides):
    from dataclasses import replace

    from app.providers.fixture_provider import FixtureProvider
    from app.providers.registry import ProviderSet

    fixture = FixtureProvider()
    base = ProviderSet(
        market=fixture,
        news=tuple(news),
        filings=fixture if filings == "fixture" else filings,
        fundamentals=fixture if filings == "fixture" else None,
        macro=fixture,
        crosscheck=None,
        llm=llm or _StubLLM(),
        not_configured=("crosscheck",),
    )
    return replace(base, **overrides)


def _run_set(providers):
    from uuid import uuid4

    from app.services.snapshots import combined_snapshot_hash

    service, repo, now = _service_with(providers)
    repo.save_snapshot.side_effect = lambda _id, _uid, market, news, *a, **k: (
        combined_snapshot_hash(market, news)
    )
    service.create(user_id=uuid4(), symbol="AAPL", now=now)
    return service, repo


def test_full_run_saves_v3_outputs_and_company_attribution() -> None:
    from app.domain.research import RoleQuality
    from app.prompts.research_interpretation import PROMPT_VERSION

    llm = _StubLLM()
    service, repo = _run_set(_full_set(news=(_StubNews("alpaca"),), llm=llm))

    assert service.versions.metrics == "eod-metrics-v3"
    assert service.versions.policy == "research-policy-v2"
    assert service.versions.response_schema == "research-run-response-v3"
    assert service.versions.workflow == "eod-research-v1"
    assert PROMPT_VERSION == "research-interpretation-v3"

    sources = repo.save_snapshot.call_args.args[4]
    by_type = {s.source_type: s for s in sources}
    assert {"filing", "insider_transaction"} <= set(by_type)
    for kind in ("filing", "insider_transaction"):
        assert by_type[kind].details is not None
        assert by_type[kind].details.company_specific is True

    kwargs = repo.save_snapshot.call_args.kwargs
    assert len(kwargs["providers"]) == 6
    assert kwargs["fundamentals"] is not None
    assert kwargs["macro"] is not None

    done = repo.finalize_success.call_args.kwargs
    assert done["interpretation"].attribution == "company"
    assert done["model_info"].prompt_version == "research-interpretation-v3"
    assert done["data_quality"].filings == RoleQuality.FRESH
    assert len(llm.calls) == 1
    assert {e.evidence_id for e in llm.calls[0]["evidence"]} == {
        s.evidence_id for s in sources
    }


def test_filing_only_evidence_still_calls_the_model() -> None:
    llm = _StubLLM()
    _, repo = _run_set(_full_set(news=(_StubNews("alpaca"),), llm=llm))

    assert llm.calls, "filings alone are evidence"
    assert repo.finalize_success.call_args.kwargs["interpretation"] is not None


def test_no_evidence_skips_the_model() -> None:
    from app.domain.research import ModelQuality

    llm = _StubLLM()
    providers = _full_set(
        news=(_StubNews("alpaca"),),
        filings=None,
        fundamentals=None,
        macro=None,
        llm=llm,
        not_configured=("filings", "fundamentals", "macro", "crosscheck"),
    )
    _, repo = _run_set(providers)

    assert llm.calls == []
    done = repo.finalize_success.call_args.kwargs
    assert done["data_quality"].model == ModelQuality.NOT_RUN
    assert done["interpretation"] is None
    assert done["model_info"] is None


def test_skip_text_names_missing_evidence() -> None:
    from datetime import UTC, datetime

    from app.agents.research_graph import create_research_graph
    from app.providers.fixture_provider import FixtureProvider
    from app.services.run_inputs import RunInputs
    from app.services.sessions import (
        latest_completed_xnys_close,
        trailing_xnys_sessions,
    )

    now = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
    cutoff = latest_completed_xnys_close(now)
    sessions = trailing_xnys_sessions(cutoff.date())
    fixture = FixtureProvider()
    market = fixture.fetch_daily_snapshot("AAPL", sessions[0], sessions[-1], now)
    market = market.model_copy(
        update={"as_of": cutoff, "latest_completed_session": sessions[-1]}
    )
    news = _StubNews("alpaca").fetch_company_news("AAPL", cutoff, now, 7, 10)
    state = create_research_graph(_StubLLM()).invoke(
        {
            "symbol": "AAPL",
            "market": market,
            "news": news,
            "inputs": RunInputs(),
            "evidence": [],
        }
    )
    assert state["interpretation"].summary == (
        "Automated interpretation was not run because no evidence was available."
    )


def test_filings_provider_failure_gives_review_and_the_run_succeeds() -> None:
    from app.domain.errors import VantageError
    from app.domain.research import ResearchStatus, RoleQuality

    class _BrokenFilings:
        name = "edgar"

        def fetch_filing_evidence(self, *args, **kwargs):
            raise VantageError(code="FILINGS_PROVIDER_FAILED", safe_message="down")

    providers = _full_set(
        news=(_StubNews("alpaca", items=[_news_item("alpaca", "Story")]),),
        filings=_BrokenFilings(),
    )
    _, repo = _run_set(providers)

    repo.finalize_failure.assert_not_called()
    done = repo.finalize_success.call_args.kwargs
    assert done["research_status"] == ResearchStatus.REVIEW
    assert "FILINGS_PROVIDER_FAILED" in [r.code for r in done["reasons"]]
    assert done["data_quality"].filings == RoleQuality.FAILED


def test_constructor_overrides_reach_the_data_stage() -> None:
    from unittest.mock import MagicMock

    market, news = _market_stub(), _StubNews("override-news")
    base = _provider_set(MagicMock(), MagicMock())
    service, repo, now = _service_with(
        base,
        market_provider=market,
        news_provider=news,
    )
    assert service.providers.market is market
    assert service.providers.news == (news,)
    assert service.market is market
    assert service.news is news
