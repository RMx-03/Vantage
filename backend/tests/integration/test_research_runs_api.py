import time
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import (
    AuthenticatedUser,
    get_current_user,
    get_research_repository,
)
from app.core.config import Settings, settings
from app.db.session import SessionFactory
from app.domain.errors import VantageError
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
    ResearchMetric,
    ResearchRun,
    ResearchStatus,
    VersionInfo,
)
from app.main import app
from app.prompts.research_interpretation import PROMPT_VERSION
from app.repositories.research_runs import ResearchRunRepository, RunningResearchRun
from app.services.research_run import (
    ResearchRunService,
    get_research_service,
)
from app.repositories.users import UserRepository
from app.services.policy import PolicyResult
from app.services.run_executor import RunExecutor, get_run_executor
from app.providers.registry import build_interpretation_provider
from tests.run_helpers import run_to_completion
from app.agents.research_graph import create_research_graph


@pytest.fixture
def test_user_id(make_user) -> UUID:
    return make_user("api")


@pytest.fixture
def other_user_id(make_user) -> UUID:
    return make_user("api-other")


@pytest.fixture
def auth_headers(test_user_id: UUID):
    return {"Authorization": f"Bearer test-token-{test_user_id}"}


@pytest.fixture
def other_auth_headers(other_user_id: UUID):
    return {"Authorization": f"Bearer test-token-{other_user_id}"}


@pytest.fixture
def sample_bars() -> list[DailyBar]:
    now = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
    bars = []
    for i in range(25):
        session_d = date(2026, 8, 10) + __import__("datetime").timedelta(days=i)
        bars.append(
            DailyBar(
                symbol="AAPL",
                session_date=session_d,
                open=150.0 + i,
                high=155.0 + i,
                low=149.0 + i,
                close=152.0 + i,
                adjusted_close=152.0 + i,
                volume=1_000_000,
                currency="USD",
                provider="mock_market",
                retrieved_at=now,
                adjustment_state="split_adjusted",
            )
        )
    return bars


@pytest.fixture
def mock_market(sample_bars: list[DailyBar]):
    market = MagicMock()
    market.name = "mock_market"
    market.calls = 0

    def fetch(
        symbol: str, start: date, end: date, retrieved_at: datetime, **kwargs: object
    ) -> MarketSnapshot:
        market.calls += 1
        now = retrieved_at
        session_shift = end - sample_bars[-1].session_date
        bars = [
            bar.model_copy(update={"session_date": bar.session_date + session_shift})
            for bar in sample_bars
        ]
        return MarketSnapshot(
            symbol=symbol,
            bars=bars,
            provider="mock_market",
            retrieved_at=now,
            as_of=now,
            latest_completed_session=end,
            content_hash="a" * 64,
            quality=ComponentQuality.FRESH,
        )

    market.fetch_daily_snapshot.side_effect = fetch
    return market


@pytest.fixture
def mock_news():
    news = MagicMock()
    news.name = "mock_news"
    news.calls = 0

    def fetch(
        symbol: str,
        cutoff: datetime,
        retrieved_at: datetime,
        lookback_days: int,
        limit: int,
    ) -> NewsSnapshot:
        news.calls += 1
        news.cutoff = cutoff
        news.retrieved_at = retrieved_at
        news.lookback_days = lookback_days
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


def test_service_shares_exchange_cutoff_across_market_news_and_persistence(
    test_user_id: UUID,
    mock_llm,
) -> None:
    request_time = datetime(2025, 11, 28, 19, 0, tzinfo=UTC)
    cutoff = datetime(2025, 11, 28, 18, 0, tzinfo=UTC)
    repo = MagicMock()
    repo.create_running.return_value = RunningResearchRun(
        id=1,
        public_id=uuid4(),
        user_id=test_user_id,
        symbol="AAPL",
        workflow_status="running",
        created_at=request_time,
        started_at=request_time,
    )
    repo.save_snapshot.return_value = "c" * 64
    repo.finalize_success.return_value = object()

    market = MagicMock()
    market.name = "mock_market"
    market.fetch_daily_snapshot.return_value = MarketSnapshot(
        symbol="AAPL",
        bars=[],
        provider=market.name,
        retrieved_at=request_time,
        as_of=request_time,
        latest_completed_session=date(2025, 11, 28),
        content_hash="a" * 64,
        quality=ComponentQuality.FRESH,
    )

    news = MagicMock()
    news.name = "mock_news"
    news.fetch_company_news.return_value = NewsSnapshot(
        symbol="AAPL",
        items=[],
        provider=news.name,
        retrieved_at=request_time,
        quality=ComponentQuality.MISSING,
    )

    service = ResearchRunService(
        repo=repo,
        market_provider=market,
        news_provider=news,
        interpretation_provider=mock_llm,
    )
    service.workflow = MagicMock()
    service.workflow.invoke.return_value = {"policy": MagicMock()}

    run_to_completion(service, user_id=test_user_id, symbol="AAPL", now=request_time)

    assert market.fetch_daily_snapshot.call_args.args[2:] == (
        date(2025, 11, 28),
        request_time,
    )
    assert news.fetch_company_news.call_args.args == (
        "AAPL",
        cutoff,
        request_time,
        7,
        10,
    )
    saved_market = repo.save_snapshot.call_args.args[2]
    assert saved_market.as_of == cutoff
    assert repo.finalize_success.call_args.kwargs["as_of"] == cutoff


def test_invalid_price_fallback_preserves_exchange_cutoff(
    test_user_id: UUID,
    mock_llm,
) -> None:
    request_time = datetime(2025, 11, 28, 19, 0, tzinfo=UTC)
    cutoff = datetime(2025, 11, 28, 18, 0, tzinfo=UTC)
    repo = MagicMock()
    repo.create_running.return_value = RunningResearchRun(
        id=1,
        public_id=uuid4(),
        user_id=test_user_id,
        symbol="AAPL",
        workflow_status="running",
        created_at=request_time,
        started_at=request_time,
    )
    repo.save_snapshot.return_value = "c" * 64
    repo.finalize_success.return_value = object()

    market = MagicMock()
    market.name = "mock_market"
    market.fetch_daily_snapshot.side_effect = VantageError(
        code="INVALID_PRICE_SERIES",
        safe_message="Market price series failed integrity checks.",
        duplicate_session_count=1,
    )

    news = MagicMock()
    news.name = "mock_news"
    news.fetch_company_news.return_value = NewsSnapshot(
        symbol="AAPL",
        items=[],
        provider=news.name,
        retrieved_at=request_time,
        quality=ComponentQuality.MISSING,
    )

    service = ResearchRunService(
        repo=repo,
        market_provider=market,
        news_provider=news,
        interpretation_provider=mock_llm,
    )
    service.workflow = MagicMock()
    service.workflow.invoke.return_value = {"policy": MagicMock()}

    run_to_completion(service, user_id=test_user_id, symbol="AAPL", now=request_time)

    saved_market = repo.save_snapshot.call_args.args[2]
    assert saved_market.as_of == cutoff
    assert saved_market.latest_completed_session == date(2025, 11, 28)
    assert repo.finalize_success.call_args.kwargs["as_of"] == cutoff


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.enabled = True
    llm.name = "gemini"
    llm.model = "gemini-2.5-flash"

    def interpret(
        *, symbol: str, metrics: list[ResearchMetric], evidence: list[NewsItem]
    ) -> AIInterpretation:
        return AIInterpretation(
            sentiment_label="positive",
            sentiment_score=0.75,
            summary="Solid performance and market resilience.",
            evidence_ids=["news-1"],
            warnings=[],
            abstained=False,
            abstention_reason=None,
        )

    llm.interpret.side_effect = interpret
    return llm


def test_disabled_model_skips_workflow_call_and_exposes_null_model_info(
    test_user_id, mock_market, mock_news, monkeypatch, executor
):
    now = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
    provider = build_interpretation_provider(
        Settings(_env_file=None, LLM_PROVIDER="disabled")
    )
    no_call = MagicMock(side_effect=AssertionError("disabled model must not be called"))
    monkeypatch.setattr(provider, "interpret", no_call)
    market = mock_market.fetch_daily_snapshot(
        "AAPL", date(2026, 8, 1), date(2026, 9, 14), now
    )
    news = mock_news.fetch_company_news("AAPL", now, now, 7, 10)
    state = create_research_graph(provider).invoke(
        {"symbol": "AAPL", "market": market, "news": news}
    )
    assert state["interpretation"] is None
    assert state["model_failure_code"] is None
    assert state["policy"].data_quality.model == ModelQuality.NOT_RUN
    assert state["policy"].metrics
    assert not any(r.code.startswith("MODEL_") for r in state["policy"].reasons)

    repo = ResearchRunRepository()
    service = ResearchRunService(
        repo=repo,
        market_provider=mock_market,
        news_provider=mock_news,
        interpretation_provider=provider,
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=test_user_id,
        email_verified=True,
    )
    app.dependency_overrides[get_research_service] = lambda: service
    app.dependency_overrides[get_run_executor] = lambda: executor
    try:
        with TestClient(app) as client:
            body = _complete(client, executor, {})
    finally:
        app.dependency_overrides.clear()
    assert body["model_info"] is None
    assert body["interpretation"] is None
    assert body["data_quality"]["model"] == "not_run"
    assert body["metrics"]
    no_call.assert_not_called()


class TrackingRepo(ResearchRunRepository):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.last_run: Any = None

    def create_running(
        self,
        user_id: UUID,
        symbol: str,
        versions: VersionInfo,
        trace_id: str | None = None,
        **kwargs: Any,
    ):
        self.events.append("create_running")
        res = super().create_running(
            user_id=user_id,
            symbol=symbol,
            versions=versions,
            trace_id=trace_id,
            **kwargs,
        )
        self.last_run = res
        return res

    def finalize_failure(
        self,
        *,
        internal_id: int,
        user_id: UUID,
        error_code: str,
        error_message_safe: str,
    ):
        res = super().finalize_failure(
            internal_id=internal_id,
            user_id=user_id,
            error_code=error_code,
            error_message_safe=error_message_safe,
        )
        self.last_run = res
        return res


@pytest.fixture
def tracking_repo():
    return TrackingRepo()


@pytest.fixture
def service(tracking_repo, mock_market, mock_news, mock_llm):
    return ResearchRunService(
        repo=tracking_repo,
        market_provider=mock_market,
        news_provider=mock_news,
        interpretation_provider=mock_llm,
    )


@pytest.fixture
def executor():
    pool = RunExecutor(max_workers=2)
    yield pool
    assert pool.wait_idle(5)
    pool.shutdown()


@pytest.fixture
def client(service, tracking_repo, executor, test_user_id: UUID, other_user_id: UUID):
    def fake_auth(request: Request) -> AuthenticatedUser:
        auth_str = request.headers.get("authorization", "") or request.headers.get(
            "Authorization", ""
        )
        if str(other_user_id) in auth_str:
            return AuthenticatedUser(id=other_user_id, email_verified=True)
        return AuthenticatedUser(id=test_user_id, email_verified=True)

    app.dependency_overrides[get_current_user] = fake_auth
    app.dependency_overrides[get_research_service] = lambda: service
    app.dependency_overrides[get_research_repository] = lambda: tracking_repo
    app.dependency_overrides[get_run_executor] = lambda: executor

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def _complete(
    client: TestClient,
    executor: RunExecutor,
    headers: dict,
    symbol: str = "AAPL",
) -> dict:
    """POST a run, wait for the detached worker, and return the stored run."""
    accepted = client.post(
        "/api/v1/research-runs", json={"symbol": symbol}, headers=headers
    )
    assert accepted.status_code == 202
    run_id = accepted.json()["run_id"]
    assert executor.wait_idle(10)
    fetched = client.get(f"/api/v1/research-runs/{run_id}", headers=headers)
    assert fetched.status_code == 200
    return fetched.json()


def test_post_persists_before_fetch_and_uses_each_provider_once(
    client: TestClient,
    executor: RunExecutor,
    auth_headers: dict,
    tracking_repo: TrackingRepo,
    mock_market,
    mock_news,
) -> None:
    data = _complete(client, executor, auth_headers)
    assert tracking_repo.events[0] == "create_running"
    assert mock_market.calls == 1
    assert mock_news.calls == 1
    assert data["workflow_status"] == "succeeded"
    assert data["symbol"] == "AAPL"


def test_market_failure_finalizes_and_stores_the_error(
    client: TestClient,
    executor: RunExecutor,
    auth_headers: dict,
    tracking_repo: TrackingRepo,
    mock_market,
) -> None:
    mock_market.fetch_daily_snapshot.side_effect = VantageError(
        code="MARKET_DATA_PROVIDER_FAILED",
        safe_message="Failed to retrieve market prices.",
    )
    body = _complete(client, executor, auth_headers)
    assert body["workflow_status"] == "failed"
    assert body["error_code"] == "MARKET_DATA_PROVIDER_FAILED"
    assert body["error_message_safe"] == "Failed to retrieve market prices."
    assert tracking_repo.last_run.workflow_status == "failed"


def test_unexpected_failure_is_sanitized_and_finalized(
    client: TestClient,
    executor: RunExecutor,
    auth_headers: dict,
    tracking_repo: TrackingRepo,
    mock_market,
) -> None:
    mock_market.fetch_daily_snapshot.side_effect = RuntimeError(
        "database-password-must-not-leak"
    )

    body = _complete(client, executor, auth_headers)

    assert body["workflow_status"] == "failed"
    assert body["error_code"] == "INTERNAL_ERROR"
    assert "password" not in body["error_message_safe"]
    assert tracking_repo.last_run.workflow_status == "failed"
    assert tracking_repo.last_run.error_code == "INTERNAL_ERROR"


def test_invalid_price_series_is_persisted_as_insufficient_data(
    client: TestClient, executor: RunExecutor, auth_headers: dict, mock_market, mock_llm
) -> None:
    mock_market.fetch_daily_snapshot.side_effect = VantageError(
        code="INVALID_PRICE_SERIES",
        safe_message="Market price series failed integrity checks.",
        duplicate_session_count=1,
    )
    body = _complete(client, executor, auth_headers)
    assert body["workflow_status"] == "succeeded"
    assert body["research_status"] == "insufficient_data"
    assert body["data_quality"]["model"] == "not_run"
    assert [
        reason["code"] for reason in body["reasons"] if reason["severity"] == "blocking"
    ] == ["INVALID_PRICE_SERIES"]
    metrics = {metric["key"]: metric["value"] for metric in body["metrics"]}
    assert metrics["price_duplicate_session_count"] == 1
    assert metrics["price_missing_value_count"] == 0
    mock_llm.interpret.assert_not_called()


def test_model_failure_is_a_persisted_degraded_success(
    client: TestClient, executor: RunExecutor, auth_headers: dict, mock_llm
) -> None:
    mock_llm.interpret.side_effect = VantageError(
        code="MODEL_UNAVAILABLE",
        safe_message="LLM service unavailable.",
    )
    body = _complete(client, executor, auth_headers)
    assert body["research_status"] == "review"
    assert body["data_quality"]["model"] == "failed"
    assert body["model_info"]["failure_code"] == "MODEL_UNAVAILABLE"
    assert body["interpretation"] == {
        "sentiment_label": "unavailable",
        "sentiment_score": None,
        "summary": "AI interpretation was unavailable for this research run.",
        "evidence_ids": [],
        "warnings": ["AI interpretation failed or was unavailable."],
        "abstained": True,
        "abstention_reason": "MODEL_UNAVAILABLE",
        "attribution": None,
    }


def test_inadequate_prices_skip_model_and_return_typed_outcome(
    client: TestClient, executor: RunExecutor, auth_headers: dict, mock_market, mock_llm
) -> None:
    """The second `model=not_run` path: the model is enabled but never called.

    No interpretation may be published or persisted for a model that never ran.
    """
    original_fetch = mock_market.fetch_daily_snapshot.side_effect

    def stale_fetch(*args, **kwargs):
        market = original_fetch(*args, **kwargs)
        return market.model_copy(update={"quality": ComponentQuality.STALE})

    mock_market.fetch_daily_snapshot.side_effect = stale_fetch
    body = _complete(client, executor, auth_headers)
    assert body["research_status"] == "insufficient_data"
    assert body["data_quality"]["model"] == "not_run"
    assert body["interpretation"] is None
    assert body["model_info"] is None
    mock_llm.interpret.assert_not_called()

    with SessionFactory() as session:
        stored = session.execute(
            text(
                "SELECT interpretation, model_provider, model_name, prompt_version "
                "FROM vantage_app.research_runs WHERE public_id = :public_id"
            ),
            {"public_id": body["run_id"]},
        ).one()
    assert stored == (None, None, None, None)


def test_no_news_evidence_skips_the_model_instead_of_reporting_it_failed(
    client: TestClient, executor: RunExecutor, auth_headers: dict, mock_news, mock_llm
) -> None:
    """With no evidence the model can only abstain: it must cite an article.

    Calling it anyway cost most of the run's time and its forced abstention was
    reported as MODEL_UNAVAILABLE, "provider unavailable or timed out", which
    was false. Production showed exactly that on 2026-10-04.
    """

    def no_news(symbol, cutoff, retrieved_at, lookback_days, limit):
        return NewsSnapshot(
            symbol=symbol,
            items=[],
            provider="mock_news",
            retrieved_at=retrieved_at,
            quality=ComponentQuality.MISSING,
        )

    mock_news.fetch_company_news.side_effect = no_news
    body = _complete(client, executor, auth_headers)
    mock_llm.interpret.assert_not_called()
    assert body["data_quality"]["news"] == "missing"
    assert body["data_quality"]["model"] == "not_run"
    assert body["interpretation"] is None
    codes = [reason["code"] for reason in body["reasons"]]
    assert "NO_RECENT_NEWS" in codes
    assert "MODEL_UNAVAILABLE" not in codes


def test_new_run_records_the_prompt_version_the_code_sends(
    client: TestClient, executor: RunExecutor, auth_headers: dict, mock_llm
) -> None:
    """Recorded provenance must name the prompt that actually produced the output."""
    body = _complete(client, executor, auth_headers)
    assert PROMPT_VERSION == "research-interpretation-v3"
    assert body["model_info"]["prompt_version"] == PROMPT_VERSION

    with SessionFactory() as session:
        stored = session.execute(
            text(
                "SELECT prompt_version FROM vantage_app.research_runs "
                "WHERE public_id = :public_id"
            ),
            {"public_id": body["run_id"]},
        ).scalar_one()
    assert stored == PROMPT_VERSION


def test_get_cross_user_returns_404(
    client: TestClient,
    executor: RunExecutor,
    auth_headers: dict,
    other_auth_headers: dict,
) -> None:
    run_id = _complete(client, executor, auth_headers)["run_id"]

    # Other user lookup must return 404
    other_resp = client.get(
        f"/api/v1/research-runs/{run_id}", headers=other_auth_headers
    )
    assert other_resp.status_code == 404

    # Owning user lookup succeeds
    owner_resp = client.get(f"/api/v1/research-runs/{run_id}", headers=auth_headers)
    assert owner_resp.status_code == 200
    assert owner_resp.json()["run_id"] == run_id


def test_list_owned_pagination(
    client: TestClient, executor: RunExecutor, auth_headers: dict
) -> None:
    for sym in ["MSFT", "GOOGL", "AMZN"]:
        _complete(client, executor, auth_headers, sym)

    page1 = client.get("/api/v1/research-runs?limit=2", headers=auth_headers)
    assert page1.status_code == 200
    p1_data = page1.json()
    assert len(p1_data["items"]) == 2
    assert p1_data["next_cursor"] is not None

    page2 = client.get(
        f"/api/v1/research-runs?limit=2&before={p1_data['next_cursor']}",
        headers=auth_headers,
    )
    assert page2.status_code == 200
    p2_data = page2.json()
    assert len(p2_data["items"]) >= 1


def test_legacy_analyze_endpoint_is_absent(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/v1/analyze", json={"ticker": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 404


def test_validation_error_uses_safe_error_envelope(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/v1/research-runs", json={"symbol": "BTC-USD"}, headers=auth_headers
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "run_id": None,
            "request_id": None,
            "retryable": False,
        }
    }


def test_invalid_cursor_is_bad_request(client: TestClient, auth_headers: dict) -> None:
    response = client.get(
        "/api/v1/research-runs?before=not-a-cursor", headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_CURSOR"


def test_finalization_conflict_is_propagated_without_opposite_finalization(
    test_user_id: UUID,
    mock_market,
    mock_news,
    mock_llm,
) -> None:
    public_id = uuid4()

    class FinalizationConflictRepository:
        def create_running(self, **kwargs: Any) -> RunningResearchRun:
            now = datetime.now(UTC)
            return RunningResearchRun(
                id=1,
                public_id=public_id,
                user_id=test_user_id,
                symbol="AAPL",
                workflow_status="running",
                created_at=now,
                started_at=now,
            )

        def save_snapshot(self, *args: Any, **kwargs: Any) -> str:
            return "c" * 64

        def finalize_success(self, **kwargs: Any) -> None:
            raise VantageError(
                code="RUN_ALREADY_FINALIZED",
                safe_message="Research run has already been finalized.",
            )

        def finalize_failure(self, **kwargs: Any) -> None:
            raise AssertionError("must not attempt failure finalization after conflict")

    service = ResearchRunService(
        repo=FinalizationConflictRepository(),  # type: ignore[arg-type]
        market_provider=mock_market,
        news_provider=mock_news,
        interpretation_provider=mock_llm,
    )
    service.workflow = MagicMock()
    service.workflow.invoke.return_value = {
        "policy": PolicyResult(
            research_status=ResearchStatus.INFORMATIONAL,
            summary="All good",
            reasons=[],
            metrics=[],
            data_quality=DataQuality(
                overall=OverallQuality.SUFFICIENT,
                prices=ComponentQuality.FRESH,
                news=ComponentQuality.FRESH,
                model=ModelQuality.HEALTHY,
            ),
            warnings=[],
            interpretation=AIInterpretation(
                sentiment_label="positive",
                sentiment_score=0.75,
                summary="All good",
            ),
        )
    }

    # `_execute` is what the detached worker runs; the worker swallows this error,
    # so call it directly to see the propagation and that no failure finalization
    # is attempted (the fake's finalize_failure would raise AssertionError).
    row = service._create_row(user_id=test_user_id, norm_symbol="AAPL", root_span=None)
    with pytest.raises(VantageError) as exc:
        service._execute(
            row,
            user_id=test_user_id,
            norm_symbol="AAPL",
            now=datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
            root_span=None,
        )

    assert exc.value.code == "RUN_ALREADY_FINALIZED"
    assert exc.value.run_id == str(public_id)


def test_run_already_finalized_maps_to_conflict(
    test_user_id: UUID,
    auth_headers: dict,
) -> None:
    public_id = uuid4()

    class ConflictService:
        def start_async(self, **kwargs: Any) -> None:
            raise VantageError(
                code="RUN_ALREADY_FINALIZED",
                safe_message="Research run has already been finalized.",
                run_id=str(public_id),
            )

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=test_user_id,
        email_verified=True,
    )
    app.dependency_overrides[get_research_service] = lambda: ConflictService()
    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/research-runs",
                json={"symbol": "AAPL"},
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "RUN_ALREADY_FINALIZED",
        "message": "Research run has already been finalized.",
        "run_id": str(public_id),
        "request_id": None,
        "retryable": False,
    }


def test_completed_response_is_v3(
    client: TestClient, executor: RunExecutor, auth_headers: dict
) -> None:
    body = _complete(client, executor, auth_headers)

    assert body["versions"]["response_schema"] == "research-run-response-v3"
    assert body["interpretation"]["evidence_ids"] == ["news-1"]
    assert body["interpretation"]["sentiment_label"] == "positive"
    assert body["interpretation"]["abstained"] is False
    assert "price_bars" not in body["snapshot"]
    assert "user_id" not in body["snapshot"]
    assert "id" not in body["snapshot"]
    assert len(body["snapshot"]["content_hash"]) == 64
    assert body["snapshot"]["market_provider"] == "mock_market"
    assert body["snapshot"]["news_provider"] == "mock_news"
    assert body["snapshot"]["news_quality"] == "fresh"

    # Provenance reports real retrieval times, never the analysis cutoff.
    cutoff = datetime.fromisoformat(body["as_of"])
    assert datetime.fromisoformat(body["snapshot"]["market_as_of"]) == cutoff
    assert datetime.fromisoformat(body["snapshot"]["news_coverage_end"]) == cutoff
    assert datetime.fromisoformat(body["snapshot"]["news_retrieved_at"]) > cutoff
    assert datetime.fromisoformat(body["snapshot"]["market_retrieved_at"]) > cutoff


def test_persisted_v2_run_is_re_readable_by_id(
    client: TestClient, executor: RunExecutor, auth_headers: dict
) -> None:
    created = _complete(client, executor, auth_headers)

    fetched = client.get(
        f"/api/v1/research-runs/{created['run_id']}", headers=auth_headers
    )

    assert fetched.status_code == 200
    assert fetched.json()["interpretation"] == created["interpretation"]
    assert fetched.json()["snapshot"] == created["snapshot"]


def test_run_records_the_immutable_code_revision(
    client: TestClient, executor: RunExecutor, auth_headers: dict
) -> None:
    created = _complete(client, executor, auth_headers)

    assert created["versions"]["code"] == settings.CODE_REVISION

    fetched = client.get(
        f"/api/v1/research-runs/{created['run_id']}", headers=auth_headers
    ).json()
    assert fetched["versions"]["code"] == settings.CODE_REVISION


def test_legacy_hostile_stored_url_is_dropped_by_the_read_path(
    client: TestClient, executor: RunExecutor, auth_headers: dict
) -> None:
    """A row persisted before the write-side allowlist must not leave the API."""
    created = _complete(client, executor, auth_headers)

    with SessionFactory() as session, session.begin():
        updated = session.execute(
            text(
                "UPDATE vantage_app.research_sources SET url = :url "
                "WHERE snapshot_id = ("
                "SELECT s.id FROM vantage_app.research_snapshots s "
                "JOIN vantage_app.research_runs r ON r.id = s.run_id "
                "WHERE r.public_id = :public_id)"
            ),
            {
                "url": "javascript:alert(document.cookie)",
                "public_id": UUID(created["run_id"]),
            },
        ).rowcount
    assert updated == 1

    fetched = client.get(
        f"/api/v1/research-runs/{created['run_id']}", headers=auth_headers
    )

    assert fetched.status_code == 200
    sources = fetched.json()["sources"]
    assert sources
    assert [s["url"] for s in sources] == [None] * len(sources)

    listed = client.get("/api/v1/research-runs?limit=10", headers=auth_headers).json()
    listed_run = next(r for r in listed["items"] if r["run_id"] == created["run_id"])
    assert [s["url"] for s in listed_run["sources"]] == [None] * len(sources)

    # A legacy row that is safe but unnormalized is served byte for byte: the
    # run's published content_hash was derived from exactly those bytes.
    unnormalized = "https://Example.com/news/a/?utm_source=x&b=2"
    with SessionFactory() as session, session.begin():
        session.execute(
            text(
                "UPDATE vantage_app.research_sources SET url = :url "
                "WHERE snapshot_id = ("
                "SELECT s.id FROM vantage_app.research_snapshots s "
                "JOIN vantage_app.research_runs r ON r.id = s.run_id "
                "WHERE r.public_id = :public_id)"
            ),
            {"url": unnormalized, "public_id": UUID(created["run_id"])},
        )

    refetched = client.get(
        f"/api/v1/research-runs/{created['run_id']}", headers=auth_headers
    )

    assert refetched.status_code == 200
    assert [s["url"] for s in refetched.json()["sources"]] == [unnormalized]


# ---------------------------------------------------------------------------
# Asynchronous opt-in
# ---------------------------------------------------------------------------


def test_post_with_prefer_async_returns_202_running_with_location(
    client: TestClient, auth_headers: dict, executor: RunExecutor
) -> None:
    response = client.post(
        "/api/v1/research-runs",
        json={"symbol": "AAPL"},
        headers={**auth_headers, "Prefer": "respond-async"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["workflow_status"] == "running"
    assert response.headers["Location"].endswith(f"/research-runs/{body['run_id']}")
    assert response.headers["Preference-Applied"] == "respond-async"

    final = body
    for _ in range(50):
        final = client.get(
            f"/api/v1/research-runs/{body['run_id']}", headers=auth_headers
        ).json()
        if final["workflow_status"] != "running":
            break
        time.sleep(0.1)
    assert final["workflow_status"] == "succeeded"


def test_post_without_prefer_still_runs_asynchronously(
    client: TestClient, auth_headers: dict, executor: RunExecutor
) -> None:
    response = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 202
    body = response.json()
    assert body["workflow_status"] == "running"
    assert response.headers["Location"].endswith(f"/research-runs/{body['run_id']}")
    # RFC 7240: only echo a preference the client actually sent.
    assert "Preference-Applied" not in response.headers
    assert executor.wait_idle(5)
    final = client.get(f"/api/v1/research-runs/{body['run_id']}", headers=auth_headers)
    assert final.json()["workflow_status"] == "succeeded"


def test_capacity_exceeded_returns_429_retry_after_and_no_row(
    client: TestClient, auth_headers: dict
) -> None:
    full = RunExecutor(max_workers=1)
    slot = full.reserve()
    app.dependency_overrides[get_run_executor] = lambda: full
    try:
        before = client.get("/api/v1/research-runs", headers=auth_headers).json()
        response = client.post(
            "/api/v1/research-runs",
            json={"symbol": "AAPL"},
            headers={**auth_headers, "Prefer": "respond-async"},
        )
        after = client.get("/api/v1/research-runs", headers=auth_headers).json()
    finally:
        slot.release()
        full.shutdown()
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "5"
    detail = response.json()["detail"]
    assert detail["code"] == "RUN_CAPACITY_EXCEEDED"
    assert detail["retryable"] is True
    assert after["items"] == before["items"]


def test_draining_returns_503_retry_after(
    client: TestClient, auth_headers: dict
) -> None:
    draining = RunExecutor(max_workers=1)
    draining.begin_drain()
    app.dependency_overrides[get_run_executor] = lambda: draining
    try:
        response = client.post(
            "/api/v1/research-runs",
            json={"symbol": "AAPL"},
            headers={**auth_headers, "Prefer": "respond-async"},
        )
    finally:
        draining.shutdown()
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    detail = response.json()["detail"]
    assert detail["code"] == "SERVICE_DRAINING"
    assert detail["retryable"] is True


def _orphan(tracking_repo, service, user_id: UUID) -> UUID:
    row = tracking_repo.create_running(
        user_id=user_id, symbol="AAPL", versions=service.versions
    )
    with SessionFactory() as session, session.begin():
        session.execute(
            text(
                "UPDATE vantage_app.research_runs "
                "SET started_at = now() - interval '200 seconds' "
                "WHERE public_id = :p"
            ),
            {"p": row.public_id},
        )
    return row.public_id


def test_get_expires_orphaned_running_run(
    client: TestClient,
    auth_headers: dict,
    executor: RunExecutor,
    tracking_repo,
    service,
    test_user_id: UUID,
) -> None:
    run_id = _orphan(tracking_repo, service, test_user_id)
    response = client.get(f"/api/v1/research-runs/{run_id}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_status"] == "failed"
    assert body["error_code"] == "RUN_INTERRUPTED"


def test_list_expires_orphaned_running_runs(
    client: TestClient,
    auth_headers: dict,
    executor: RunExecutor,
    tracking_repo,
    service,
    test_user_id: UUID,
) -> None:
    run_id = _orphan(tracking_repo, service, test_user_id)
    page = client.get("/api/v1/research-runs", headers=auth_headers).json()
    item = next(i for i in page["items"] if i["run_id"] == str(run_id))
    assert item["workflow_status"] == "failed"
    assert item["error_code"] == "RUN_INTERRUPTED"


def test_run_records_provider_roles(
    tracking_repo: TrackingRepo,
    mock_llm,
    client: TestClient,
    executor: RunExecutor,
    auth_headers: dict,
    test_user_id: UUID,
) -> None:
    from app.providers.fixture_provider import FixtureProvider

    fixture = FixtureProvider()
    svc = ResearchRunService(
        repo=tracking_repo,
        market_provider=fixture,
        news_provider=fixture,
        interpretation_provider=mock_llm,
    )
    app.dependency_overrides[get_research_service] = lambda: svc

    body = _complete(client, executor, auth_headers)
    records = {r["role"]: r for r in body["snapshot"]["providers"]}
    assert len(body["snapshot"]["providers"]) == 6
    assert records["market"]["provider"] == "fixture"
    assert records["news"]["provider"] == "fixture"
    for role in ("filings", "fundamentals", "macro", "crosscheck"):
        assert records[role]["quality"] == "not_configured"
        assert records[role]["provider"] is None
        assert records[role]["retrieved_at"] is None
    dq = body["data_quality"]
    for key in ("filings", "fundamentals", "macro", "crosscheck"):
        assert dq.get(key) == "not_configured"
    stored = tracking_repo.get_owned(test_user_id, UUID(body["run_id"]))
    assert stored is not None and stored.snapshot is not None
    assert stored.snapshot.providers is not None
    assert len(stored.snapshot.providers) == 6
