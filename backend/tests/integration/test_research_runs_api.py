from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.api.deps import (
    AuthenticatedUser,
    get_current_user,
    get_research_repository,
)
from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DailyBar,
    EvidenceSource,
    MarketSnapshot,
    ModelInfo,
    NewsItem,
    NewsSnapshot,
    ResearchMetric,
    VersionInfo,
)
from app.main import app
from app.repositories.research_runs import ResearchRunRepository
from app.services.research_run import (
    ResearchRunService,
    get_research_service,
)


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

    def fetch(symbol: str, start: date, end: date) -> MarketSnapshot:
        market.calls += 1
        now = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
        return MarketSnapshot(
            symbol=symbol,
            bars=sample_bars,
            provider="mock_market",
            retrieved_at=now,
            as_of=now,
            latest_completed_session=sample_bars[-1].session_date,
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

    def fetch(symbol: str, as_of: datetime, limit: int) -> NewsSnapshot:
        news.calls += 1
        now = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
        item = NewsItem(
            evidence_id="news-1",
            provider="mock_news",
            publisher="Reuters",
            title="Apple quarterly progress",
            url="https://example.com/news-1",
            event_time=now,
            retrieved_at=now,
            content_hash="b" * 64,
        )
        return NewsSnapshot(
            symbol=symbol,
            items=[item],
            provider="mock_news",
            retrieved_at=now,
            coverage_start=now,
            coverage_end=now,
            quality=ComponentQuality.FRESH,
        )

    news.fetch_company_news.side_effect = fetch
    return news


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.name = "gemini"
    llm.model = "gemini-2.5-flash"

    def interpret(*, symbol: str, metrics: list[ResearchMetric], news: NewsSnapshot) -> AIInterpretation:
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


class TrackingRepo(ResearchRunRepository):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.last_run: Any = None

    def create_running(self, user_id: UUID, symbol: str, versions: VersionInfo, trace_id: str | None = None, **kwargs: Any):
        self.events.append("create_running")
        res = super().create_running(user_id=user_id, symbol=symbol, versions=versions, trace_id=trace_id, **kwargs)
        self.last_run = res
        return res

    def finalize_failure(self, *, internal_id: int, user_id: UUID, error_code: str, error_message_safe: str):
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
        auth_str = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
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
    client: TestClient, auth_headers: dict, tracking_repo: TrackingRepo, mock_market, mock_news
) -> None:
    response = client.post("/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers)
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
    response = client.post("/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "MARKET_DATA_PROVIDER_FAILED"
    assert detail["run_id"]
    assert tracking_repo.last_run.workflow_status == "failed"


def test_model_failure_is_a_persisted_degraded_success(
    client: TestClient, auth_headers: dict, mock_llm
) -> None:
    mock_llm.interpret.side_effect = VantageError(
        code="MODEL_UNAVAILABLE",
        safe_message="LLM service unavailable.",
    )
    response = client.post("/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["research_status"] == "review"
    assert body["data_quality"]["model"] == "failed"
    assert body["model_info"]["failure_code"] == "MODEL_UNAVAILABLE"


def test_get_cross_user_returns_404(
    client: TestClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    create_resp = client.post("/api/v1/research-runs", json={"symbol": "AAPL"}, headers=auth_headers)
    assert create_resp.status_code == 201
    run_id = create_resp.json()["run_id"]

    # Other user lookup must return 404
    other_resp = client.get(f"/api/v1/research-runs/{run_id}", headers=other_auth_headers)
    assert other_resp.status_code == 404

    # Owning user lookup succeeds
    owner_resp = client.get(f"/api/v1/research-runs/{run_id}", headers=auth_headers)
    assert owner_resp.status_code == 200
    assert owner_resp.json()["run_id"] == run_id


def test_list_owned_pagination(client: TestClient, auth_headers: dict) -> None:
    for sym in ["MSFT", "GOOGL", "AMZN"]:
        r = client.post("/api/v1/research-runs", json={"symbol": sym}, headers=auth_headers)
        assert r.status_code == 201

    page1 = client.get("/api/v1/research-runs?limit=2", headers=auth_headers)
    assert page1.status_code == 200
    p1_data = page1.json()
    assert len(p1_data["items"]) == 2
    assert p1_data["next_cursor"] is not None

    page2 = client.get(f"/api/v1/research-runs?limit=2&before={p1_data['next_cursor']}", headers=auth_headers)
    assert page2.status_code == 200
    p2_data = page2.json()
    assert len(p2_data["items"]) >= 1


def test_analyze_compat_endpoint(client: TestClient, auth_headers: dict) -> None:
    response = client.post("/api/v1/analyze", json={"ticker": "AAPL"}, headers=auth_headers)
    assert response.status_code in {200, 201}
    assert response.json()["workflow_status"] == "succeeded"
    assert "approved" not in response.json()
