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
from app.repositories.research_runs import ResearchRunRepository, RunningResearchRun
from app.services.research_run import (
    ResearchRunService,
    get_research_service,
)
from app.services.policy import PolicyResult
from app.providers.llm import build_interpretation_provider
from app.agents.research_graph import create_research_graph


@pytest.fixture
def test_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def other_user_id() -> UUID:
    return uuid4()


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
        symbol: str, start: date, end: date, retrieved_at: datetime
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

    service.create(user_id=test_user_id, symbol="AAPL", now=request_time)

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

    service.create(user_id=test_user_id, symbol="AAPL", now=request_time)

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
        *, symbol: str, metrics: list[ResearchMetric], news: NewsSnapshot
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
    test_user_id, mock_market, mock_news, monkeypatch
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

    class MemoryRepo:
        def create_running(self, *, versions, **kwargs):
            self.versions = versions
            self.row = RunningResearchRun(
                id=1,
                public_id=uuid4(),
                user_id=test_user_id,
                symbol="AAPL",
                workflow_status="running",
                created_at=now,
                started_at=now,
            )
            return self.row

        def save_snapshot(self, internal_id, user_id, market, news, sources):
            self.sources = sources
            return "c" * 64

        def finalize_success(self, *, internal_id, user_id, **kwargs):
            return ResearchRun(
                run_id=self.row.public_id,
                symbol="AAPL",
                created_at=now,
                completed_at=now,
                workflow_status="succeeded",
                sources=self.sources,
                snapshot=None,
                versions=self.versions,
                **kwargs,
            )

    service = ResearchRunService(
        repo=MemoryRepo(),
        market_provider=mock_market,
        news_provider=mock_news,
        interpretation_provider=provider,
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=test_user_id
    )
    app.dependency_overrides[get_research_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/research-runs", json={"symbol": "AAPL"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    body = response.json()
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
def client(service, tracking_repo, test_user_id: UUID, other_user_id: UUID):
    def fake_auth(request: Request) -> AuthenticatedUser:
        auth_str = request.headers.get("authorization", "") or request.headers.get(
            "Authorization", ""
        )
        if str(other_user_id) in auth_str:
            return AuthenticatedUser(id=other_user_id)
        return AuthenticatedUser(id=test_user_id)

    app.dependency_overrides[get_current_user] = fake_auth
    app.dependency_overrides[get_research_service] = lambda: service
    app.dependency_overrides[get_research_repository] = lambda: tracking_repo

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_post_persists_before_fetch_and_uses_each_provider_once(
    client: TestClient,
    auth_headers: dict,
    tracking_repo: TrackingRepo,
    mock_market,
    mock_news,
) -> None:
    response = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 201
    assert tracking_repo.events[0] == "create_running"
    assert mock_market.calls == 1
    assert mock_news.calls == 1
    data = response.json()
    assert data["workflow_status"] == "succeeded"
    assert data["symbol"] == "AAPL"


def test_market_failure_finalizes_and_returns_run_id(
    client: TestClient, auth_headers: dict, tracking_repo: TrackingRepo, mock_market
) -> None:
    mock_market.fetch_daily_snapshot.side_effect = VantageError(
        code="MARKET_DATA_PROVIDER_FAILED",
        safe_message="Failed to retrieve market prices.",
    )
    response = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "MARKET_DATA_PROVIDER_FAILED"
    assert detail["run_id"]
    assert tracking_repo.last_run.workflow_status == "failed"


def test_unexpected_failure_is_sanitized_and_finalized(
    client: TestClient, auth_headers: dict, tracking_repo: TrackingRepo, mock_market
) -> None:
    mock_market.fetch_daily_snapshot.side_effect = RuntimeError(
        "database-password-must-not-leak"
    )

    response = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "INTERNAL_ERROR"
    assert detail["run_id"]
    assert "password" not in detail["message"]
    assert tracking_repo.last_run.workflow_status == "failed"
    assert tracking_repo.last_run.error_code == "INTERNAL_ERROR"


def test_invalid_price_series_is_persisted_as_insufficient_data(
    client: TestClient, auth_headers: dict, mock_market, mock_llm
) -> None:
    mock_market.fetch_daily_snapshot.side_effect = VantageError(
        code="INVALID_PRICE_SERIES",
        safe_message="Market price series failed integrity checks.",
        duplicate_session_count=1,
    )
    response = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
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
    client: TestClient, auth_headers: dict, mock_llm
) -> None:
    mock_llm.interpret.side_effect = VantageError(
        code="MODEL_UNAVAILABLE",
        safe_message="LLM service unavailable.",
    )
    response = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
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
    }


def test_inadequate_prices_skip_model_and_return_typed_outcome(
    client: TestClient, auth_headers: dict, mock_market, mock_llm
) -> None:
    """The second `model=not_run` path: the model is enabled but never called.

    No interpretation may be published or persisted for a model that never ran.
    """
    original_fetch = mock_market.fetch_daily_snapshot.side_effect

    def stale_fetch(*args, **kwargs):
        market = original_fetch(*args, **kwargs)
        return market.model_copy(update={"quality": ComponentQuality.STALE})

    mock_market.fetch_daily_snapshot.side_effect = stale_fetch
    response = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["research_status"] == "insufficient_data"
    assert body["data_quality"]["model"] == "not_run"
    assert body["interpretation"] is None
    mock_llm.interpret.assert_not_called()

    with SessionFactory() as session:
        stored = session.execute(
            text(
                "SELECT interpretation FROM vantage_app.research_runs "
                "WHERE public_id = :public_id"
            ),
            {"public_id": body["run_id"]},
        ).scalar_one()
    assert stored is None


def test_get_cross_user_returns_404(
    client: TestClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    create_resp = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )
    assert create_resp.status_code == 201
    run_id = create_resp.json()["run_id"]

    # Other user lookup must return 404
    other_resp = client.get(
        f"/api/v1/research-runs/{run_id}", headers=other_auth_headers
    )
    assert other_resp.status_code == 404

    # Owning user lookup succeeds
    owner_resp = client.get(f"/api/v1/research-runs/{run_id}", headers=auth_headers)
    assert owner_resp.status_code == 200
    assert owner_resp.json()["run_id"] == run_id


def test_list_owned_pagination(client: TestClient, auth_headers: dict) -> None:
    for sym in ["MSFT", "GOOGL", "AMZN"]:
        r = client.post(
            "/api/v1/research-runs", json={"symbol": sym}, headers=auth_headers
        )
        assert r.status_code == 201

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

    with pytest.raises(VantageError) as exc:
        service.create(
            user_id=test_user_id,
            symbol="AAPL",
            now=datetime(2026, 9, 14, 21, 0, tzinfo=UTC),
        )

    assert exc.value.code == "RUN_ALREADY_FINALIZED"
    assert exc.value.run_id == str(public_id)


def test_run_already_finalized_maps_to_conflict(
    test_user_id: UUID,
    auth_headers: dict,
) -> None:
    public_id = uuid4()

    class ConflictService:
        def create(self, **kwargs: Any) -> None:
            raise VantageError(
                code="RUN_ALREADY_FINALIZED",
                safe_message="Research run has already been finalized.",
                run_id=str(public_id),
            )

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=test_user_id
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


def test_completed_response_is_v2(client: TestClient, auth_headers: dict) -> None:
    response = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()

    assert body["versions"]["response_schema"] == "research-run-response-v2"
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
    client: TestClient, auth_headers: dict
) -> None:
    created = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    ).json()

    fetched = client.get(
        f"/api/v1/research-runs/{created['run_id']}", headers=auth_headers
    )

    assert fetched.status_code == 200
    assert fetched.json()["interpretation"] == created["interpretation"]
    assert fetched.json()["snapshot"] == created["snapshot"]


def test_run_records_the_immutable_code_revision(
    client: TestClient, auth_headers: dict
) -> None:
    created = client.post(
        "/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers
    ).json()

    assert created["versions"]["code"] == settings.CODE_REVISION

    fetched = client.get(
        f"/api/v1/research-runs/{created['run_id']}", headers=auth_headers
    ).json()
    assert fetched["versions"]["code"] == settings.CODE_REVISION
