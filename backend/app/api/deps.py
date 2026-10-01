from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from app.core.security.tokens import decode_access_token
from app.domain.auth import AUTH_EMAIL_UNVERIFIED
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
    # Required, with no default. It gates research runs, so it must never fail
    # open: code that forgets it is a validation error, not a verified user.
    email_verified: bool


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
        return AuthenticatedUser(
            id=claims.subject, email_verified=claims.email_verified
        )


async def require_verified_user(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Allow only accounts that have confirmed their email address.

    Read from the token claim, so this costs no database query. The cost is a
    lag of at most one access-token lifetime between verifying and being able
    to act; the frontend calls refresh after verification to close it.
    """
    if not user.email_verified:
        raise VantageError(
            code=AUTH_EMAIL_UNVERIFIED,
            safe_message="Confirm your email address before starting a research run.",
        )
    return user


def get_research_repository() -> ResearchRunRepository:
    return ResearchRunRepository()
