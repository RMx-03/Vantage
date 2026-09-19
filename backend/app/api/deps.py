from uuid import UUID
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from app.core.database import supabase_client
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
    """
    FastAPI dependency that validates a Supabase JWT and returns an AuthenticatedUser.
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
            # The Supabase SDK verifies tokens synchronously; keep that blocking
            # call off the event loop so concurrent requests are not stalled.
            response = await run_in_threadpool(supabase_client.auth.get_user, token)
            # The SDK may return no response at all; an absent response is an
            # unverified token, so it fails closed exactly like an absent user.
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
