from uuid import UUID
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from app.core.database import supabase_client
from app.core.security.tokens import decode_access_token
from app.domain.auth import AUTH_TOKEN_EXPIRED
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
    """Resolve the caller from a bearer token.

    Vantage-issued JWTs are verified locally — no network call. During Phase 2A
    only, a token this backend did not issue falls through to Supabase so the
    deployed application keeps working while the frontend has not yet cut over.

    PHASE 2B MUST DELETE THE SUPABASE FALLBACK. Leaving it in place would be a
    standing authentication bypass through a third party we no longer use.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("authenticate_request"):
        if credentials is None or not credentials.credentials:
            raise VantageError(
                code="AUTH_REQUIRED",
                safe_message="Authentication is required.",
            )

        token = credentials.credentials

        try:
            claims = decode_access_token(token)
            return AuthenticatedUser(id=claims.subject)
        except VantageError as error:
            # A token we issued and that has merely expired is ours, and the
            # caller needs to know to refresh rather than re-authenticate.
            # Only an unrecognisable token falls through to the legacy path.
            if error.code == AUTH_TOKEN_EXPIRED:
                raise

        try:
            response = await run_in_threadpool(supabase_client.auth.get_user, token)
            user = response.user if response is not None else None
            if user is None or not hasattr(user, "id"):
                raise ValueError("No user returned from authentication service")
            return AuthenticatedUser(id=UUID(str(user.id)))
        except Exception:
            raise VantageError(
                code="AUTH_INVALID",
                safe_message="Authentication credentials are invalid or expired.",
            )


def get_research_repository() -> ResearchRunRepository:
    return ResearchRunRepository()
