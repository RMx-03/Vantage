"""Research Workbench routes (ADR-0008). Every route is 404 while the flag is off."""

import csv
import io
import json
from collections.abc import Iterator
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.deps import AuthenticatedUser, get_current_user, require_verified_user
from app.api.errors import vantage_error_response
from app.core.config import settings
from app.domain.errors import RUN_CAPACITY_EXCEEDED, SERVICE_DRAINING, VantageError
from app.domain.experiments import (
    ExperimentPlan,
    ExperimentRecord,
    ExperimentSpec,
    ExperimentSummary,
)
from app.services.experiments import (
    ExperimentService,
    get_experiment_executor,
    get_experiment_service,
)
from app.services.run_executor import RunExecutor

_RETRY_AFTER_SECONDS = "5"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_CSV_COLUMNS = ["section", "date", "symbol", "field", "value"]


def _workbench_enabled() -> None:
    if not settings.RESEARCH_WORKBENCH_ENABLED:
        raise VantageError(code="NOT_FOUND", safe_message="Not found.")


router = APIRouter(tags=["experiments"], dependencies=[Depends(_workbench_enabled)])

Service = Annotated[ExperimentService, Depends(get_experiment_service)]
Executor = Annotated[RunExecutor, Depends(get_experiment_executor)]
Reader = Annotated[AuthenticatedUser, Depends(get_current_user)]
Writer = Annotated[AuthenticatedUser, Depends(require_verified_user)]


def _accepted(start: Any) -> JSONResponse:
    try:
        record: ExperimentRecord = start()
    except VantageError as exc:
        if exc.code in {RUN_CAPACITY_EXCEEDED, SERVICE_DRAINING}:
            return vantage_error_response(
                exc, headers={"Retry-After": _RETRY_AFTER_SECONDS}
            )
        raise
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=jsonable_encoder(record),
        headers={"Location": f"{settings.API_V1_PREFIX}/experiments/{record.id}"},
    )


@router.post("/plan", response_model=ExperimentPlan)
def plan_experiment(
    spec: ExperimentSpec, user: Reader, service: Service
) -> ExperimentPlan:
    """Size an experiment without fetching data or starting anything."""
    return service.plan(spec)


@router.post("", response_model=ExperimentRecord, status_code=status.HTTP_202_ACCEPTED)
def create_experiment(
    spec: ExperimentSpec, user: Writer, service: Service, executor: Executor
) -> JSONResponse:
    """Start a simulation; poll the `Location` for the outcome."""
    return _accepted(lambda: service.start(user.id, spec, executor))


@router.get("", response_model=list[ExperimentSummary])
def list_experiments(
    user: Reader,
    service: Service,
    executor: Executor,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[ExperimentSummary]:
    """The owner's experiments, newest first, as summaries."""
    return service.list(user.id, limit, executor)


@router.get("/{experiment_id}", response_model=ExperimentRecord)
def get_experiment(
    experiment_id: UUID, user: Reader, service: Service, executor: Executor
) -> ExperimentRecord:
    return service.get(user.id, experiment_id, executor)


@router.post(
    "/{experiment_id}/replay",
    response_model=ExperimentRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
def replay_experiment(
    experiment_id: UUID, user: Writer, service: Service, executor: Executor
) -> JSONResponse:
    """Re-run a finished experiment from its frozen inputs, with no provider call."""
    return _accepted(lambda: service.replay(user.id, experiment_id, executor))


@router.get("/{experiment_id}/export")
def export_experiment(
    experiment_id: UUID,
    user: Reader,
    service: Service,
    executor: Executor,
    format: Literal["json", "csv"] = "json",
) -> Response:
    """Derived data only: spec, metrics, series, trades, findings, versions."""
    record = service.get(user.id, experiment_id, executor)
    filename = f"experiment-{record.id}.{format}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if format == "json":
        return JSONResponse(content=jsonable_encoder(record), headers=headers)
    return Response(
        content=_csv(record), media_type="text/csv; charset=utf-8", headers=headers
    )


@router.delete("/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experiment(experiment_id: UUID, user: Reader, service: Service) -> None:
    service.delete(user.id, experiment_id)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    # Spreadsheets run cells that start like a formula; a quote keeps them text.
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def _rows(record: ExperimentRecord) -> Iterator[tuple[str, Any, Any, str, Any]]:
    for field, value in record.spec.model_dump(mode="json").items():
        yield "spec", None, None, field, value
    yield "result", None, None, "status", record.status.value
    yield "result", None, None, "label", record.label
    result = record.result
    if result is not None:
        yield "result", None, None, "research_status", result.research_status.value
        yield "result", None, None, "result_hash", result.result_hash
        for section, metrics in (
            ("metrics", result.metrics),
            ("benchmark_metrics", result.benchmark_metrics),
        ):
            if metrics is not None:
                for field, value in metrics.model_dump(mode="json").items():
                    yield section, None, None, field, value
        if result.series is not None:
            series = result.series
            for i, day in enumerate(series.dates):
                yield "series", day, None, "nav", series.nav[i]
                yield "series", day, None, "gross_nav", series.gross_nav[i]
                if series.benchmark_nav is not None:
                    yield "series", day, None, "benchmark_nav", series.benchmark_nav[i]
        for trade in result.trades:
            for field in ("shares", "price", "notional"):
                yield "trade", trade.session, trade.symbol, field, getattr(trade, field)
        for finding in result.findings:
            yield "finding", None, finding.symbol, finding.code, finding.message
    for field, value in sorted(record.versions.items()):
        yield "version", None, None, field, value


def _csv(record: ExperimentRecord) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    for section, day, symbol, field, value in _rows(record):
        writer.writerow(
            [
                section,
                day.isoformat() if day else "",
                _cell(symbol),
                field,
                _cell(value),
            ]
        )
    return buffer.getvalue()
