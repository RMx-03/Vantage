import hashlib
import hmac
from typing import Any, Mapping
from uuid import UUID

from opentelemetry.sdk.trace import Event, ReadableSpan, SpanProcessor
from opentelemetry.trace import Status, StatusCode

ALLOWED_ATTRIBUTES = frozenset(
    {
        "vantage.run_id",
        "vantage.request_id",
        "vantage.user_hash",
        "vantage.instrument_symbol",
        "vantage.workflow_version",
        "vantage.response_schema_version",
        "vantage.prompt_version",
        "vantage.snapshot_hash",
        "vantage.workflow_status",
        "vantage.research_status",
        "vantage.quality.overall",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "error.type",
    }
)


def user_hash(user_id: UUID, salt: str) -> str:
    """
    Generate a pseudonymous, irreversible SHA-256 HMAC of a user ID using a secret salt.
    """
    return hmac.HMAC(salt.encode("utf-8"), user_id.bytes, hashlib.sha256).hexdigest()


def safe_attributes(values: Mapping[str, Any]) -> dict[str, Any]:
    """
    Filter arbitrary attributes against the strict allowlist.
    Never exports unapproved keys, secrets, or identifiers.
    """
    return {key: value for key, value in values.items() if key in ALLOWED_ATTRIBUTES}


class RedactingSpanProcessor(SpanProcessor):
    """
    SpanProcessor that sanitizes span attributes before export.
    Strips any attribute not in ALLOWED_ATTRIBUTES.
    """

    def on_start(self, span, parent_context=None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        attrs = getattr(span, "_attributes", None)
        d = getattr(attrs, "_dict", None) if attrs is not None else None
        if d is not None:
            unallowed = [k for k in list(d.keys()) if k not in ALLOWED_ATTRIBUTES]
            for k in unallowed:
                del d[k]
        elif isinstance(attrs, dict):
            unallowed = [k for k in list(attrs.keys()) if k not in ALLOWED_ATTRIBUTES]
            for k in unallowed:
                del attrs[k]

        events = getattr(span, "_events", None)
        if events is not None:
            span._events = [
                Event(event.name, attributes={}, timestamp=event.timestamp)
                for event in events
            ]

        current_status = span.status
        if (
            current_status.status_code == StatusCode.ERROR
            and current_status.description
        ):
            span._status = Status(StatusCode.ERROR, "Operation failed.")

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
