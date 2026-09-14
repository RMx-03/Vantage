from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    AuthenticatedUser,
    get_current_user,
    get_research_repository,
    get_research_service,
)
from app.domain.errors import SafeError
from app.domain.research import ResearchRun, ResearchRunPage, ResearchRunRequest
from app.repositories.research_runs import ResearchRunRepository
from app.services.research_run import ResearchRunService

router = APIRouter(tags=["research-runs"])


@router.post("", response_model=ResearchRun, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ResearchRun, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_run(
    request: ResearchRunRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ResearchRunService = Depends(get_research_service),
) -> ResearchRun:
    """
    Create and synchronously execute a durable, bounded research run.
    """
    return service.create(user_id=user.id, symbol=request.symbol, now=datetime.now(UTC))


@router.get("/{run_id}", response_model=ResearchRun)
def get_run(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRunRepository = Depends(get_research_repository),
) -> ResearchRun:
    """
    Retrieve an owner-scoped research run by its public run_id.
    """
    run = repo.get_owned(user_id=user.id, public_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=SafeError(code="RUN_NOT_FOUND", message="Research run was not found.").model_dump(),
        )
    return run


@router.get("", response_model=ResearchRunPage)
@router.get("/", response_model=ResearchRunPage, include_in_schema=False)
def list_runs(
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRunRepository = Depends(get_research_repository),
) -> ResearchRunPage:
    """
    List owner-scoped research runs with keyset/cursor pagination.
    """
    return repo.list_owned(user_id=user.id, limit=limit, before=before)
