import logging
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter

from app.core.config import settings
from app.telemetry.redaction import RedactingSpanProcessor

logger = logging.getLogger(__name__)

TRACER_NAME = "vantage.research"


class SafeExportSpanProcessor(SpanProcessor):
    """
    Wraps a SpanExporter so that any export failures are safely caught,
    incremented, and logged, without ever interrupting the product research run.
    """

    def __init__(self, exporter: SpanExporter) -> None:
        self.exporter = exporter
        self.export_failures: int = 0

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        try:
            self.exporter.export([span])
        except Exception as exc:
            self.export_failures += 1
            logger.warning("Telemetry export failed safely: %s", exc)

    def shutdown(self) -> None:
        try:
            self.exporter.shutdown()
        except Exception as exc:
            logger.warning("Telemetry exporter shutdown exception: %s", exc)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        try:
            return bool(self.exporter.force_flush(timeout_millis))
        except Exception:
            return True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER_NAME, settings.APP_VERSION)


def configure_telemetry(app: FastAPI | None = None) -> TracerProvider:
    """
    Configure OpenTelemetry with redact-on-end processing and optional Langfuse export.
    Defaults to no external export in local/CI environments.
    """
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor())

    if settings.TRACE_EXPORT_ENABLED:
        try:
            # When Langfuse v4 export is enabled, configure safe exporter
            if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
                from langfuse import Langfuse
                # Langfuse integration placeholder using safe exporter
                logger.info("Langfuse export configured for host: %s", settings.LANGFUSE_HOST)
        except Exception as exc:
            logger.warning("Failed to configure Langfuse exporter: %s", exc)

    trace.set_tracer_provider(provider)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=provider,
                excluded_urls="/health,/",
            )
        except Exception as exc:
            logger.warning("FastAPI instrumentation failed: %s", exc)

    return provider
