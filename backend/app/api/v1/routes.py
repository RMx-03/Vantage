from datetime import UTC, datetime
import logging

from fastapi import APIRouter, Depends, status

from app.api.deps import AuthenticatedUser, get_current_user, get_research_service
from app.api.v1.research_runs import router as research_runs_router
from app.domain.research import ResearchRun
from app.models.schemas import AnalyzeRequest
from app.services.research_run import ResearchRunService

from app.telemetry.tracing import get_tracer

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(research_runs_router, prefix="/research-runs")


@router.post(
    "/analyze",
    deprecated=True,
    response_model=ResearchRun,
    status_code=status.HTTP_200_OK,
    summary="Deprecated: Run financial research analysis",
    description="Deprecated adapter endpoint. Please migrate to POST /api/v1/research-runs.",
)
def analyze_compat(
    request: AnalyzeRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ResearchRunService = Depends(get_research_service),
) -> ResearchRun:
    """
    Deprecated compatibility endpoint mapping ticker to the durable ResearchRunService.
    Does not expose approval boolean.
    """
    logger.info("[analyze_compat] Received deprecated analysis request for: %s", request.ticker)
    tracer = get_tracer()
    with tracer.start_as_current_span("research_run") as root_span:
        run = service.create(
            user_id=user.id,
            symbol=request.ticker,
            now=datetime.now(UTC),
            root_span=root_span,
        )
        with tracer.start_as_current_span("serialize_response") as s_span:
            s_span.set_attribute("vantage.run_id", str(run.run_id))
            return run
