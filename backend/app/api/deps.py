from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from app.core.database import supabase_client
from app.repositories.research_runs import ResearchRunRepository
from app.services.research_run import (
    ResearchRunService,
    get_research_service as get_research_service,
)


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
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization credentials.",
        )

    token = credentials.credentials

    try:
        response = supabase_client.auth.get_user(token)
        user = response.user
        if user is None or not hasattr(user, "id"):
            raise ValueError("No user returned from authentication service")
        return AuthenticatedUser(id=UUID(str(user.id)))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


def get_research_repository() -> ResearchRunRepository:
    return ResearchRunRepository()

