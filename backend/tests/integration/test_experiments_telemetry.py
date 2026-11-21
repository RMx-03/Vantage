"""Experiment spans carry allowlisted attributes only, never the owner's text."""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.telemetry.redaction import ALLOWED_ATTRIBUTES, RedactingSpanProcessor
from tests.integration.test_experiments_api import (
    BASE,
    SPEC,
    WAIT,
    _headers,
    client,  # noqa: F401  (fixture)
    executor,  # noqa: F401  (fixture)
    history,  # noqa: F401  (fixture)
)
from tests.integration.test_experiments_service import FakeHistory

pytestmark = pytest.mark.integration

PRIVATE = {
    "question": "Private question about my watchlist",
    "hypothesis": "Private hypothesis text",
    "notes": "Private notes text",
}


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter
    exporter.clear()


@pytest.mark.parametrize(
    ("history", "error"),
    [(FakeHistory(), None), (FakeHistory(blank="MSFT"), "SYMBOL_NOT_FOUND")],
)
def test_experiment_spans_are_allowlisted_and_private(
    spans: InMemorySpanExporter,
    client,  # noqa: F811
    executor,  # noqa: F811
    make_user,
    error: str | None,
) -> None:
    user = make_user("trace-exp")
    response = client.post(BASE, json={**SPEC, **PRIVATE}, headers=_headers(user))
    assert response.status_code == 202
    assert executor.wait_idle(WAIT)

    finished = spans.get_finished_spans()
    execute = [s for s in finished if s.name == "experiment_execute"]
    assert len(execute) == 1
    assert execute[0].attributes.get("error.type") == error
    for span in finished:
        assert set(span.attributes or {}) <= ALLOWED_ATTRIBUTES
    encoded = repr([(s.name, dict(s.attributes or {})) for s in finished])
    for text in PRIVATE.values():
        assert text not in encoded
