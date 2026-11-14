from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from opentelemetry import trace

from app.api.deps import (
    AuthenticatedUser,
    get_current_user,
    get_research_repository,
    get_research_service,
    require_verified_user,
)
from app.api.errors import vantage_error_response
from app.domain.errors import (
    RUN_CAPACITY_EXCEEDED,
    SERVICE_DRAINING,
    SafeError,
    VantageError,
)
from app.domain.research import ResearchRun, ResearchRunPage, ResearchRunRequest
from app.repositories.research_runs import ResearchRunRepository
from app.services.research_run import ResearchRunService
from app.services.run_executor import RunExecutor, get_run_executor
from app.services.run_expiry import expire_stale_runs

from app.telemetry.tracing import get_tracer

router = APIRouter(tags=["research-runs"])

_ASYNC_PREFERENCE = "respond-async"
_RETRY_AFTER_SECONDS = "5"
_ACCEPTED_RESPONSES: dict[int | str, dict[str, Any]] = {
    202: {
        "model": ResearchRun,
        "description": "Run accepted; poll GET /research-runs/{run_id}",
    }
}


@router.post(
    "",
    response_model=ResearchRun,
    status_code=status.HTTP_201_CREATED,
    responses=_ACCEPTED_RESPONSES,
)
@router.post(
    "/",
    response_model=ResearchRun,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_run(
    request: ResearchRunRequest,
    prefer: Annotated[str | None, Header()] = None,
    user: AuthenticatedUser = Depends(require_verified_user),
    service: ResearchRunService = Depends(get_research_service),
    executor: RunExecutor = Depends(get_run_executor),
) -> ResearchRun | JSONResponse:
    """
    Create a durable, bounded research run.

    Executes synchronously and returns 201 by default. With
    `Prefer: respond-async` the run is accepted (202) and executes in the
    background; poll `GET /research-runs/{run_id}` for the outcome.
    """
    tracer = get_tracer()
    root_span = trace.get_current_span()
    if prefer is not None and _ASYNC_PREFERENCE in prefer.lower():
        try:
            accepted = service.start_async(
                user_id=user.id,
                symbol=request.symbol,
                now=datetime.now(UTC),
                executor=executor,
                root_span=root_span if root_span.is_recording() else None,
            )
        except VantageError as exc:
            if exc.code in {RUN_CAPACITY_EXCEEDED, SERVICE_DRAINING}:
                return vantage_error_response(
                    exc, headers={"Retry-After": _RETRY_AFTER_SECONDS}
                )
            raise
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=jsonable_encoder(accepted),
            headers={
                "Location": f"/api/v1/research-runs/{accepted.run_id}",
                "Preference-Applied": _ASYNC_PREFERENCE,
            },
        )
    run = service.create(
        user_id=user.id,
        symbol=request.symbol,
        now=datetime.now(UTC),
        root_span=root_span if root_span.is_recording() else None,
    )
    with tracer.start_as_current_span("serialize_response") as s_span:
        s_span.set_attribute("vantage.run_id", str(run.run_id))
        return run


@router.get("/{run_id}", response_model=ResearchRun)
def get_run(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRunRepository = Depends(get_research_repository),
    executor: RunExecutor = Depends(get_run_executor),
) -> ResearchRun:
    """
    Retrieve an owner-scoped research run by its public run_id.
    """
    expire_stale_runs(repo, executor, now=datetime.now(UTC), user_id=user.id)
    run = repo.get_owned(user_id=user.id, public_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=SafeError(
                code="RUN_NOT_FOUND", message="Research run was not found."
            ).model_dump(),
        )
    return run


@router.get("", response_model=ResearchRunPage)
@router.get("/", response_model=ResearchRunPage, include_in_schema=False)
def list_runs(
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: ResearchRunRepository = Depends(get_research_repository),
    executor: RunExecutor = Depends(get_run_executor),
) -> ResearchRunPage:
    """
    List owner-scoped research runs with keyset/cursor pagination.
    """
    expire_stale_runs(repo, executor, now=datetime.now(UTC), user_id=user.id)
    return repo.list_owned(user_id=user.id, limit=limit, before=before)
