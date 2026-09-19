from datetime import UTC, date, datetime
import hmac
import hashlib
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.api.deps import AuthenticatedUser, get_current_user, get_research_repository
from app.core.config import settings
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DailyBar,
    MarketSnapshot,
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
from app.telemetry.redaction import (
    ALLOWED_ATTRIBUTES,
    RedactingSpanProcessor,
    safe_attributes,
    user_hash,
)
from app.telemetry.tracing import (
    TRACER_NAME,
    SafeExportSpanProcessor,
    configure_telemetry,
    get_tracer,
)


@pytest.fixture
def test_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def secret_token() -> str:
    return "secret-token-super-secret-12345"


@pytest.fixture
def user_email() -> str:
    return "trader@example.com"


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

    def fetch(
        symbol: str, start: date, end: date, retrieved_at: datetime
    ) -> MarketSnapshot:
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
def mock_llm():
    llm = MagicMock()
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


@pytest.fixture
def service(mock_market, mock_news, mock_llm):
    return ResearchRunService(
        repo=ResearchRunRepository(),
        market_provider=mock_market,
        news_provider=mock_news,
        interpretation_provider=mock_llm,
    )


@pytest.fixture
def memory_exporter():
    return InMemorySpanExporter()


@pytest.fixture
def traced_client(
    memory_exporter, service, test_user_id: UUID, secret_token: str, user_email: str
):
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
    trace.set_tracer_provider(provider)

    def fake_auth(request: Request) -> AuthenticatedUser:
        tracer = get_tracer()
        with tracer.start_as_current_span("authenticate_request"):
            return AuthenticatedUser(id=test_user_id)

    app.dependency_overrides[get_current_user] = fake_auth
    app.dependency_overrides[get_research_service] = lambda: service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    memory_exporter.clear()


class FailingExporter(SpanExporter):
    def export(self, spans):
        raise RuntimeError("Langfuse exporter network failure!")

    def shutdown(self):
        pass


class ResultFailingExporter(SpanExporter):
    def export(self, spans):
        return SpanExportResult.FAILURE

    def shutdown(self):
        pass


def test_export_failure_result_is_counted() -> None:
    processor = SafeExportSpanProcessor(ResultFailingExporter())

    processor.on_end(MagicMock())

    assert processor.export_failures == 1


def test_exporter_lifecycle_failures_are_isolated() -> None:
    exporter = MagicMock()
    exporter.shutdown.side_effect = RuntimeError("shutdown-secret")
    exporter.force_flush.side_effect = RuntimeError("flush-secret")
    processor = SafeExportSpanProcessor(exporter)

    processor.shutdown()

    assert processor.force_flush(125) is True


def test_redaction_supports_plain_attribute_mappings() -> None:
    span = MagicMock()
    span._attributes = {
        "vantage.run_id": "safe-run-id",
        "authorization": "Bearer secret-token",
    }
    span._events = None
    span.status = Status(StatusCode.UNSET)
    processor = RedactingSpanProcessor()

    processor.on_end(span)

    assert span._attributes == {"vantage.run_id": "safe-run-id"}
    assert processor.force_flush() is True
    assert processor.shutdown() is None


@pytest.fixture
def client_with_failing_exporter(service, test_user_id: UUID):
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor())
    provider.add_span_processor(SafeExportSpanProcessor(FailingExporter()))
    trace.set_tracer_provider(provider)

    def fake_auth(request: Request) -> AuthenticatedUser:
        tracer = get_tracer()
        with tracer.start_as_current_span("authenticate_request"):
            return AuthenticatedUser(id=test_user_id)

    app.dependency_overrides[get_current_user] = fake_auth
    app.dependency_overrides[get_research_service] = lambda: service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_redaction_helpers(test_user_id: UUID) -> None:
    h1 = user_hash(test_user_id, "salt1")
    h2 = user_hash(test_user_id, "salt1")
    h3 = user_hash(test_user_id, "salt2")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64

    filtered = safe_attributes(
        {
            "vantage.run_id": "123",
            "user.email": "leak@example.com",
            "authorization": "Bearer token",
            "vantage.workflow_status": "succeeded",
        }
    )
    assert "vantage.run_id" in filtered
    assert "vantage.workflow_status" in filtered
    assert "user.email" not in filtered
    assert "authorization" not in filtered


def test_trace_has_stable_tree_and_run_correlation(
    traced_client: TestClient, memory_exporter: InMemorySpanExporter, secret_token: str
) -> None:
    response = traced_client.post(
        "/api/v1/research-runs",
        json={"symbol": "AAPL"},
        headers={"Authorization": f"Bearer {secret_token}"},
    )
    assert response.status_code == 201
    spans = memory_exporter.get_finished_spans()
    span_names = {s.name for s in spans}
    expected_spans = {
        "research_run",
        "authenticate_request",
        "create_run_record",
        "fetch_market_snapshot",
        "fetch_news_snapshot",
        "calculate_metrics",
        "generate_interpretation",
        "apply_research_policy",
        "persist_result",
        "serialize_response",
    }
    assert span_names >= expected_spans

    run_id = response.json()["run_id"]
    for s in spans:
        if s.name != "authenticate_request":
            assert s.attributes.get("vantage.run_id") == run_id

    research_span = next(span for span in spans if span.name == "research_run")
    for span in spans:
        if span.name in expected_spans - {"research_run"}:
            assert span.context.trace_id == research_span.context.trace_id
    auth_span = next(span for span in spans if span.name == "authenticate_request")
    assert auth_span.parent is not None
    assert auth_span.parent.span_id == research_span.context.span_id


def test_secrets_and_identity_are_never_exported(
    traced_client: TestClient,
    memory_exporter: InMemorySpanExporter,
    secret_token: str,
    test_user_id: UUID,
    user_email: str,
) -> None:
    traced_client.post(
        "/api/v1/research-runs",
        json={"symbol": "AAPL"},
        headers={"Authorization": f"Bearer {secret_token}"},
    )
    spans = memory_exporter.get_finished_spans()
    encoded = repr(spans)
    assert secret_token not in encoded
    assert str(test_user_id) not in encoded
    assert user_email not in encoded
    assert "postgresql" not in encoded


def test_export_failure_does_not_change_run_result(
    client_with_failing_exporter: TestClient, secret_token: str
) -> None:
    response = client_with_failing_exporter.post(
        "/api/v1/research-runs",
        json={"symbol": "AAPL"},
        headers={"Authorization": f"Bearer {secret_token}"},
    )
    assert response.status_code == 201
    assert response.json()["workflow_status"] == "succeeded"


def test_redaction_removes_exception_event_and_status_details() -> None:
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = get_tracer()
    with tracer.start_as_current_span(
        "redaction-test", record_exception=False, set_status_on_exception=False
    ) as span:
        span.set_attribute("authorization", "Bearer secret-value")
        span.add_event(
            "exception",
            {
                "exception.type": "RuntimeError",
                "exception.message": "database-password-secret",
                "exception.stacktrace": "stack database-password-secret",
            },
        )
        span.set_status(Status(StatusCode.ERROR, "database-password-secret"))

    exported = exporter.get_finished_spans()[0]
    assert "secret" not in repr(exported.events)
    assert all(not event.attributes for event in exported.events)
    assert exported.status.description == "Operation failed."
    assert "authorization" not in exported.attributes


def test_configure_telemetry_registers_langfuse_with_shared_provider(
    monkeypatch,
) -> None:
    from app.telemetry import tracing

    captured: dict[str, Any] = {}

    class FakeLangfuse:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)
    monkeypatch.setattr(settings, "TRACE_EXPORT_ENABLED", True)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-test")
    provider = tracing.configure_telemetry()
    assert captured["tracer_provider"] is provider
    assert captured["public_key"] == "pk-test"
    assert captured["secret_key"] == "sk-test"
    assert callable(captured["should_export_span"])
    should_export = captured["should_export_span"]
    assert should_export(MagicMock(instrumentation_scope=None)) is False
    matching_span = MagicMock()
    matching_span.instrumentation_scope.name = TRACER_NAME
    assert should_export(matching_span) is True


def test_langfuse_configuration_failure_is_sanitized(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.telemetry import tracing

    class BrokenLangfuse:
        def __init__(self, **kwargs):
            raise RuntimeError("langfuse-secret-must-not-leak")

    monkeypatch.setattr("langfuse.Langfuse", BrokenLangfuse)
    monkeypatch.setattr(settings, "TRACE_EXPORT_ENABLED", True)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setattr(trace, "set_tracer_provider", lambda provider: None)

    provider = tracing.configure_telemetry()

    assert isinstance(provider, TracerProvider)
    assert tracing._langfuse_client is None
    assert "langfuse-secret" not in caplog.text


def test_fastapi_instrumentation_failure_does_not_break_startup(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    monkeypatch.setattr(settings, "TRACE_EXPORT_ENABLED", False)
    monkeypatch.setattr(trace, "set_tracer_provider", lambda provider: None)
    monkeypatch.setattr(
        FastAPIInstrumentor,
        "instrument_app",
        MagicMock(side_effect=RuntimeError("instrumentation-secret-must-not-leak")),
    )

    provider = configure_telemetry(FastAPI())

    assert isinstance(provider, TracerProvider)
    assert "instrumentation-secret" not in caplog.text
