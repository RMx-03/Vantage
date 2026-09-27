from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from app.core.security.tokens import decode_access_token
from app.domain.errors import VantageError
from app.repositories.research_runs import ResearchRunRepository
from app.services.research_run import (
    ResearchRunService,
    get_research_service as get_research_service,
)
from app.telemetry.tracing import get_tracer


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID


_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """Resolve the caller from a Vantage-issued access token.

    Verification is local: no network call, no third-party dependency on the
    request path.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("authenticate_request"):
        if credentials is None or not credentials.credentials:
            raise VantageError(
                code="AUTH_REQUIRED",
                safe_message="Authentication is required.",
            )
        claims = decode_access_token(credentials.credentials)
        return AuthenticatedUser(id=claims.subject)


def get_research_repository() -> ResearchRunRepository:
    return ResearchRunRepository()
