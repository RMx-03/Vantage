"""Detached research runs: start, execute off the request, and stale expiry.

Execution is made deterministic with an interpretation stub that blocks on a
``threading.Event``, so tests never rely on sleeps or timing.
"""

import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text

from app.db.session import SessionFactory
from app.domain.errors import (
    RUN_CAPACITY_EXCEEDED,
    RUN_DEADLINE_EXCEEDED,
    RUN_DEADLINE_EXCEEDED_MESSAGE,
    RUN_INTERRUPTED,
    RUN_INTERRUPTED_MESSAGE,
    VantageError,
)
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DailyBar,
    MarketSnapshot,
    NewsItem,
    NewsSnapshot,
    ResearchMetric,
    VersionInfo,
    WorkflowStatus,
)
from app.repositories.research_runs import ResearchRunRepository, RunningResearchRun
from app.services import research_run as research_run_module
from app.services.research_run import ResearchRunService
from app.services.run_executor import RunExecutor
from app.services.run_expiry import expire_stale_runs

NOW = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
GATE_TIMEOUT = 10.0


class TrackingRepo(ResearchRunRepository):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def create_running(
        self,
        user_id: UUID,
        symbol: str,
        versions: VersionInfo,
        trace_id: str | None = None,
    ) -> RunningResearchRun:
        self.events.append("create_running")
        return super().create_running(
            user_id=user_id, symbol=symbol, versions=versions, trace_id=trace_id
        )


class GatedInterpreter:
    """Interpretation stub whose ``interpret`` waits until the test releases it."""

    enabled = True
    name = "gemini"
    model = "gemini-2.5-flash"

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.gate = threading.Event()

    def interpret(
        self, *, symbol: str, metrics: list[ResearchMetric], evidence: list[NewsItem]
    ) -> AIInterpretation:
        self.entered.set()
        if not self.gate.wait(GATE_TIMEOUT):
            raise AssertionError("test never released the interpretation gate")
        return AIInterpretation(
            sentiment_label="positive",
            sentiment_score=0.75,
            summary="Solid performance and market resilience.",
            evidence_ids=["news-1"],
            warnings=[],
            abstained=False,
            abstention_reason=None,
        )


def _bars() -> list[DailyBar]:
    return [
        DailyBar(
            symbol="AAPL",
            session_date=date(2026, 8, 10) + timedelta(days=i),
            open=150.0 + i,
            high=155.0 + i,
            low=149.0 + i,
            close=152.0 + i,
            adjusted_close=152.0 + i,
            volume=1_000_000,
            currency="USD",
            provider="mock_market",
            retrieved_at=NOW,
            adjustment_state="split_adjusted",
        )
        for i in range(25)
    ]


@pytest.fixture
def mock_market() -> MagicMock:
    market = MagicMock()
    market.name = "mock_market"
    sample_bars = _bars()

    def fetch(
        symbol: str, start: date, end: date, retrieved_at: datetime, **kwargs: object
    ) -> MarketSnapshot:
        shift = end - sample_bars[-1].session_date
        bars = [
            bar.model_copy(update={"session_date": bar.session_date + shift})
            for bar in sample_bars
        ]
        return MarketSnapshot(
            symbol=symbol,
            bars=bars,
            provider="mock_market",
            retrieved_at=retrieved_at,
            as_of=retrieved_at,
            latest_completed_session=end,
            content_hash="a" * 64,
            quality=ComponentQuality.FRESH,
        )

    market.fetch_daily_snapshot.side_effect = fetch
    return market


@pytest.fixture
def mock_news() -> MagicMock:
    news = MagicMock()
    news.name = "mock_news"

    def fetch(
        symbol: str,
        cutoff: datetime,
        retrieved_at: datetime,
        lookback_days: int,
        limit: int,
    ) -> NewsSnapshot:
        item = NewsItem(
            evidence_id="news-1",
            provider="mock_news",
            publisher="Reuters",
            title="Apple quarterly progress",
            url="https://example.com/news-1",
            event_time=cutoff,
            retrieved_at=retrieved_at,
            content_hash="b" * 64,
        )
        return NewsSnapshot(
            symbol=symbol,
            items=[item],
            provider="mock_news",
            retrieved_at=retrieved_at,
            coverage_start=cutoff,
            coverage_end=cutoff,
            quality=ComponentQuality.FRESH,
        )

    news.fetch_company_news.side_effect = fetch
    return news


@pytest.fixture
def user_id(make_user: Any) -> UUID:
    return make_user("async-run")


@pytest.fixture
def repo() -> TrackingRepo:
    return TrackingRepo()


@pytest.fixture
def llm() -> Iterator[GatedInterpreter]:
    stub = GatedInterpreter()
    yield stub
    stub.gate.set()


@pytest.fixture
def executor(llm: GatedInterpreter) -> Iterator[RunExecutor]:
    pool = RunExecutor(max_workers=2)
    yield pool
    llm.gate.set()
    assert pool.wait_idle(5)


@pytest.fixture
def service(
    repo: TrackingRepo,
    mock_market: MagicMock,
    mock_news: MagicMock,
    llm: GatedInterpreter,
) -> ResearchRunService:
    return ResearchRunService(
        repo=repo,
        market_provider=mock_market,
        news_provider=mock_news,
        interpretation_provider=llm,
    )


def _age_run(public_id: UUID, seconds: int) -> None:
    with SessionFactory() as session, session.begin():
        session.execute(
            text(
                "UPDATE vantage_app.research_runs "
                "SET started_at = started_at - make_interval(secs => :secs) "
                "WHERE public_id = :public_id"
            ),
            {"secs": seconds, "public_id": public_id},
        )


def test_start_async_returns_running_before_model_finishes(
    service: ResearchRunService,
    repo: TrackingRepo,
    executor: RunExecutor,
    llm: GatedInterpreter,
    user_id: UUID,
) -> None:
    run = service.start_async(
        user_id=user_id, symbol=" aapl ", now=NOW, executor=executor
    )

    assert run.workflow_status == WorkflowStatus.RUNNING
    assert run.symbol == "AAPL"
    assert executor.is_in_flight(run.run_id)

    assert llm.entered.wait(GATE_TIMEOUT)
    llm.gate.set()
    assert executor.wait_idle(5)

    finished = repo.get_owned(user_id, run.run_id)
    assert finished is not None
    assert finished.workflow_status == WorkflowStatus.SUCCEEDED
    assert finished.metrics
    assert not executor.is_in_flight(run.run_id)


def test_start_async_at_capacity_creates_no_row(
    service: ResearchRunService,
    repo: TrackingRepo,
    llm: GatedInterpreter,
    user_id: UUID,
) -> None:
    single = RunExecutor(max_workers=1)
    try:
        service.start_async(user_id=user_id, symbol="AAPL", now=NOW, executor=single)
        assert llm.entered.wait(GATE_TIMEOUT)

        with pytest.raises(VantageError) as excinfo:
            service.start_async(
                user_id=user_id, symbol="MSFT", now=NOW, executor=single
            )

        assert excinfo.value.code == RUN_CAPACITY_EXCEEDED
        assert excinfo.value.retryable is True
        assert repo.events.count("create_running") == 1
    finally:
        llm.gate.set()
        assert single.wait_idle(5)


class _InlineSlot:
    """Runs the detached work inline at launch, the fastest possible finish."""

    def __init__(self, executor: "_InlineExecutor") -> None:
        self._executor = executor

    def launch(self, run_id: UUID, fn: Any) -> None:
        self._executor.launched = True
        fn()

    def release(self) -> None:
        self._executor.released = True


class _InlineExecutor:
    def __init__(self) -> None:
        self.launched = False
        self.released = False

    def reserve(self) -> _InlineSlot:
        return _InlineSlot(self)


def test_start_async_returns_running_even_when_run_finishes_instantly(
    service: ResearchRunService,
    repo: TrackingRepo,
    llm: GatedInterpreter,
    user_id: UUID,
) -> None:
    llm.gate.set()
    inline = _InlineExecutor()

    run = service.start_async(
        user_id=user_id,
        symbol="AAPL",
        now=NOW,
        executor=inline,  # type: ignore[arg-type]
    )

    assert inline.launched
    assert run.workflow_status == WorkflowStatus.RUNNING
    finished = repo.get_owned(user_id, run.run_id)
    assert finished is not None
    assert finished.workflow_status == WorkflowStatus.SUCCEEDED


def test_start_async_with_ungated_model_returns_running_then_succeeds(
    service: ResearchRunService,
    repo: TrackingRepo,
    executor: RunExecutor,
    llm: GatedInterpreter,
    user_id: UUID,
) -> None:
    llm.gate.set()

    run = service.start_async(
        user_id=user_id, symbol="AAPL", now=NOW, executor=executor
    )
    assert executor.wait_idle(5)

    assert run.workflow_status == WorkflowStatus.RUNNING
    finished = repo.get_owned(user_id, run.run_id)
    assert finished is not None
    assert finished.workflow_status == WorkflowStatus.SUCCEEDED


def test_start_async_read_back_failure_releases_slot_without_launch(
    service: ResearchRunService,
    repo: TrackingRepo,
    executor: RunExecutor,
    user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(user_id: UUID, public_id: UUID) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(repo, "get_owned", broken)

    with pytest.raises(RuntimeError):
        service.start_async(user_id=user_id, symbol="AAPL", now=NOW, executor=executor)

    assert executor.in_flight_count == 0
    assert repo.events.count("create_running") == 1


def test_start_async_row_failure_releases_slot(
    service: ResearchRunService,
    repo: TrackingRepo,
    executor: RunExecutor,
    user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(**kwargs: Any) -> RunningResearchRun:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(repo, "create_running", broken)

    with pytest.raises(RuntimeError):
        service.start_async(user_id=user_id, symbol="AAPL", now=NOW, executor=executor)

    assert executor.in_flight_count == 0


def test_detached_market_failure_is_persisted_and_slot_freed(
    service: ResearchRunService,
    repo: TrackingRepo,
    executor: RunExecutor,
    mock_market: MagicMock,
    user_id: UUID,
) -> None:
    mock_market.fetch_daily_snapshot.side_effect = VantageError(
        code="MARKET_DATA_PROVIDER_FAILED",
        safe_message="Market data provider failed.",
    )

    run = service.start_async(
        user_id=user_id, symbol="AAPL", now=NOW, executor=executor
    )
    assert executor.wait_idle(5)

    finished = repo.get_owned(user_id, run.run_id)
    assert finished is not None
    assert finished.workflow_status == WorkflowStatus.FAILED
    assert finished.error_code == "MARKET_DATA_PROVIDER_FAILED"
    assert executor.in_flight_count == 0


def test_detached_unexpected_exception_finalizes_internal_error(
    service: ResearchRunService,
    repo: TrackingRepo,
    executor: RunExecutor,
    mock_market: MagicMock,
    user_id: UUID,
) -> None:
    mock_market.fetch_daily_snapshot.side_effect = RuntimeError("provider exploded")

    run = service.start_async(
        user_id=user_id, symbol="AAPL", now=NOW, executor=executor
    )
    assert executor.wait_idle(5)

    finished = repo.get_owned(user_id, run.run_id)
    assert finished is not None
    assert finished.workflow_status == WorkflowStatus.FAILED
    assert finished.error_code == "INTERNAL_ERROR"
    assert executor.in_flight_count == 0


def test_expire_marks_orphan_interrupted_and_owned_deadline_exceeded(
    service: ResearchRunService,
    repo: TrackingRepo,
    executor: RunExecutor,
    llm: GatedInterpreter,
    user_id: UUID,
) -> None:
    orphan = repo.create_running(
        user_id=user_id, symbol="MSFT", versions=service.versions
    )
    _age_run(orphan.public_id, 200)

    owned = service.start_async(
        user_id=user_id, symbol="AAPL", now=NOW, executor=executor
    )
    assert llm.entered.wait(GATE_TIMEOUT)
    _age_run(owned.run_id, 200)

    changed = expire_stale_runs(repo, executor, now=datetime.now(UTC), user_id=user_id)

    assert changed == 2
    a = repo.get_owned(user_id, orphan.public_id)
    assert a is not None
    assert a.workflow_status == WorkflowStatus.FAILED
    assert a.error_code == RUN_INTERRUPTED
    assert a.error_message_safe == RUN_INTERRUPTED_MESSAGE
    b = repo.get_owned(user_id, owned.run_id)
    assert b is not None
    assert b.workflow_status == WorkflowStatus.FAILED
    assert b.error_code == RUN_DEADLINE_EXCEEDED
    assert b.error_message_safe == RUN_DEADLINE_EXCEEDED_MESSAGE

    llm.gate.set()
    assert executor.wait_idle(5)

    late = repo.get_owned(user_id, owned.run_id)
    assert late is not None
    assert late.workflow_status == WorkflowStatus.FAILED
    assert late.error_code == RUN_DEADLINE_EXCEEDED
    assert executor.in_flight_count == 0


def test_expire_ignores_fresh_running_rows(
    service: ResearchRunService,
    repo: TrackingRepo,
    executor: RunExecutor,
    user_id: UUID,
) -> None:
    fresh = repo.create_running(
        user_id=user_id, symbol="MSFT", versions=service.versions
    )

    changed = expire_stale_runs(repo, executor, now=datetime.now(UTC), user_id=user_id)

    assert changed == 0
    row = repo.get_owned(user_id, fresh.public_id)
    assert row is not None
    assert row.workflow_status == WorkflowStatus.RUNNING


def test_detached_execution_span_links_to_request_span(
    service: ResearchRunService,
    executor: RunExecutor,
    llm: GatedInterpreter,
    user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(research_run_module, "get_tracer", lambda: tracer)
    llm.gate.set()

    with tracer.start_as_current_span("research_run") as request_span:
        run = service.start_async(
            user_id=user_id,
            symbol="AAPL",
            now=NOW,
            executor=executor,
            root_span=request_span,
        )
    assert executor.wait_idle(5)

    spans = exporter.get_finished_spans()
    request = next(s for s in spans if s.name == "research_run")
    execute = next(s for s in spans if s.name == "research_run_execute")
    assert execute.parent is None
    assert [link.context.span_id for link in execute.links] == [request.context.span_id]
    assert execute.attributes["vantage.run_id"] == str(run.run_id)
    assert execute.attributes["vantage.workflow_status"] == "succeeded"
    assert request.attributes["vantage.run_id"] == str(run.run_id)
