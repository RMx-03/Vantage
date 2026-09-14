import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.db.models import ResearchRunRow, ResearchSnapshotRow, ResearchSourceRow
from app.db.session import SessionFactory
from app.domain.errors import VantageError
from app.domain.research import (
    ComponentQuality,
    DataQuality,
    EvidenceSource,
    MarketSnapshot,
    ModelInfo,
    ModelQuality,
    OverallQuality,
    Reason,
    ResearchMetric,
    ResearchRun,
    ResearchRunPage,
    ResearchStatus,
    VersionInfo,
    WorkflowStatus,
)


@dataclass(frozen=True)
class RunningResearchRun:
    id: int
    public_id: UUID
    user_id: UUID
    symbol: str
    workflow_status: str
    created_at: datetime
    started_at: datetime

    @property
    def run_id(self) -> UUID:
        return self.public_id


class ResearchRunRepository:
    def create_running(
        self,
        user_id: UUID,
        symbol: str,
        versions: VersionInfo,
    ) -> RunningResearchRun:
        now = datetime.now(UTC)
        normalized_symbol = symbol.strip().upper()
        with SessionFactory() as session:
            with session.begin():
                row = ResearchRunRow(
                    public_id=uuid4(),
                    user_id=user_id,
                    symbol=normalized_symbol,
                    workflow_status=WorkflowStatus.RUNNING.value,
                    research_status=None,
                    created_at=now,
                    started_at=now,
                    completed_at=None,
                    as_of=None,
                    reasons=[],
                    metrics=[],
                    data_quality=None,
                    warnings=[],
                    summary=None,
                    response_schema_version=versions.response_schema,
                    workflow_version=versions.workflow,
                    metrics_version=versions.metrics,
                    code_version=versions.code,
                )
                session.add(row)
                session.flush()
                return RunningResearchRun(
                    id=row.id,
                    public_id=row.public_id,
                    user_id=row.user_id,
                    symbol=row.symbol,
                    workflow_status=row.workflow_status,
                    created_at=row.created_at,
                    started_at=row.started_at,
                )

    def save_snapshot(
        self,
        internal_id: int,
        snapshot: MarketSnapshot,
        sources: list[EvidenceSource],
    ) -> None:
        with SessionFactory() as session:
            with session.begin():
                run = session.scalars(
                    select(ResearchRunRow).where(ResearchRunRow.id == internal_id)
                ).first()
                if run is None:
                    raise VantageError(
                        code="RUN_NOT_FOUND",
                        safe_message="Research run not found.",
                    )

                if snapshot.bars:
                    window_start = datetime.combine(
                        snapshot.bars[0].session_date,
                        datetime.min.time(),
                        tzinfo=UTC,
                    )
                    window_end = datetime.combine(
                        snapshot.bars[-1].session_date,
                        datetime.max.time(),
                        tzinfo=UTC,
                    )
                else:
                    window_start = snapshot.as_of
                    window_end = snapshot.as_of

                if window_end < window_start:
                    window_end = window_start

                quality_dict: dict[str, Any] = {
                    "overall": (
                        snapshot.quality.value
                        if hasattr(snapshot.quality, "value")
                        else str(snapshot.quality)
                    )
                }

                snapshot_row = ResearchSnapshotRow(
                    public_id=uuid4(),
                    run_id=internal_id,
                    user_id=run.user_id,
                    symbol=snapshot.symbol,
                    market_provider=snapshot.provider,
                    window_start=window_start,
                    window_end=window_end,
                    as_of=snapshot.as_of,
                    retrieved_at=snapshot.retrieved_at,
                    content_hash=snapshot.content_hash,
                    price_bars=[bar.model_dump(mode="json") for bar in snapshot.bars],
                    quality=quality_dict,
                )
                session.add(snapshot_row)
                session.flush()

                for s in sources:
                    source_row = ResearchSourceRow(
                        snapshot_id=snapshot_row.id,
                        evidence_id=s.evidence_id,
                        source_type=getattr(s, "source_type", "news"),
                        provider=s.provider,
                        publisher=s.publisher or "",
                        title=s.title,
                        url=s.url or "",
                        event_time=s.event_time or s.retrieved_at,
                        retrieved_at=s.retrieved_at,
                        content_hash=s.content_hash or "",
                    )
                    session.add(source_row)

    def finalize_success(
        self,
        *,
        internal_id: int,
        user_id: UUID,
        research_status: ResearchStatus,
        as_of: datetime,
        reasons: list[Reason],
        metrics: list[ResearchMetric],
        data_quality: DataQuality,
        warnings: list[str],
        summary: str,
        model_info: ModelInfo | None = None,
    ) -> ResearchRun:
        with SessionFactory() as session:
            with session.begin():
                stmt = (
                    select(ResearchRunRow)
                    .options(
                        selectinload(ResearchRunRow.snapshot).selectinload(
                            ResearchSnapshotRow.sources
                        )
                    )
                    .where(
                        ResearchRunRow.id == internal_id,
                        ResearchRunRow.user_id == user_id,
                    )
                )
                row = session.scalars(stmt).first()
                if row is None:
                    raise VantageError(
                        code="RUN_NOT_FOUND",
                        safe_message="Research run not found.",
                    )

                row.workflow_status = WorkflowStatus.SUCCEEDED.value
                row.research_status = research_status.value
                row.completed_at = datetime.now(UTC)
                row.as_of = as_of
                row.reasons = [r.model_dump(mode="json") for r in reasons]
                row.metrics = [m.model_dump(mode="json") for m in metrics]
                row.data_quality = data_quality.model_dump(mode="json")
                row.warnings = warnings
                row.summary = summary
                if model_info is not None:
                    row.model_provider = model_info.provider
                    row.model_name = model_info.model
                    row.prompt_version = model_info.prompt_version
                session.flush()
                return self._row_to_domain(row)

    def finalize_failure(
        self,
        *,
        internal_id: int,
        user_id: UUID,
        error_code: str,
        error_message_safe: str,
    ) -> ResearchRun:
        with SessionFactory() as session:
            with session.begin():
                stmt = (
                    select(ResearchRunRow)
                    .options(
                        selectinload(ResearchRunRow.snapshot).selectinload(
                            ResearchSnapshotRow.sources
                        )
                    )
                    .where(
                        ResearchRunRow.id == internal_id,
                        ResearchRunRow.user_id == user_id,
                    )
                )
                row = session.scalars(stmt).first()
                if row is None:
                    raise VantageError(
                        code="RUN_NOT_FOUND",
                        safe_message="Research run not found.",
                    )

                row.workflow_status = WorkflowStatus.FAILED.value
                row.research_status = ResearchStatus.FAILED.value
                row.completed_at = datetime.now(UTC)
                row.error_code = error_code
                row.error_message_safe = error_message_safe
                session.flush()
                return self._row_to_domain(row)

    def get_owned(
        self,
        user_id: UUID,
        public_id: UUID,
    ) -> ResearchRun | None:
        with SessionFactory() as session:
            stmt = (
                select(ResearchRunRow)
                .options(
                    selectinload(ResearchRunRow.snapshot).selectinload(
                        ResearchSnapshotRow.sources
                    )
                )
                .where(
                    ResearchRunRow.public_id == public_id,
                    ResearchRunRow.user_id == user_id,
                )
            )
            row = session.scalars(stmt).first()
            if row is None:
                return None
            return self._row_to_domain(row)

    def list_owned(
        self,
        user_id: UUID,
        limit: int = 10,
        before: str | None = None,
    ) -> ResearchRunPage:
        capped_limit = min(max(1, limit), 50)
        cursor_filter = None
        if before is not None:
            try:
                decoded_bytes = base64.urlsafe_b64decode(before.encode("utf-8"))
                payload = json.loads(decoded_bytes.decode("utf-8"))
                cursor_created_at = datetime.fromisoformat(payload["created_at"])
                cursor_id = int(payload["id"])
            except Exception as e:
                raise VantageError(
                    code="INVALID_CURSOR",
                    safe_message="The history cursor is invalid.",
                ) from e

            cursor_filter = or_(
                ResearchRunRow.created_at < cursor_created_at,
                and_(
                    ResearchRunRow.created_at == cursor_created_at,
                    ResearchRunRow.id < cursor_id,
                ),
            )

        with SessionFactory() as session:
            stmt = (
                select(ResearchRunRow)
                .options(
                    selectinload(ResearchRunRow.snapshot).selectinload(
                        ResearchSnapshotRow.sources
                    )
                )
                .where(ResearchRunRow.user_id == user_id)
            )
            if cursor_filter is not None:
                stmt = stmt.where(cursor_filter)
            stmt = (
                stmt.order_by(
                    ResearchRunRow.created_at.desc(),
                    ResearchRunRow.id.desc(),
                ).limit(capped_limit + 1)
            )
            rows = list(session.scalars(stmt).all())

        has_more = len(rows) > capped_limit
        page_rows = rows[:capped_limit]

        next_cursor = None
        if has_more and page_rows:
            last_row = page_rows[-1]
            cursor_payload = json.dumps(
                {
                    "created_at": last_row.created_at.isoformat(),
                    "id": last_row.id,
                }
            )
            next_cursor = base64.urlsafe_b64encode(
                cursor_payload.encode("utf-8")
            ).decode("utf-8")

        items = [self._row_to_domain(r) for r in page_rows]
        return ResearchRunPage(items=items, next_cursor=next_cursor)

    def _row_to_domain(self, row: ResearchRunRow) -> ResearchRun:
        sources: list[EvidenceSource] = []
        if row.snapshot is not None and row.snapshot.sources:
            for s in row.snapshot.sources:
                sources.append(
                    EvidenceSource(
                        evidence_id=s.evidence_id,
                        provider=s.provider,
                        publisher=s.publisher if s.publisher else None,
                        title=s.title,
                        url=s.url if s.url else None,
                        event_time=s.event_time,
                        retrieved_at=s.retrieved_at,
                        content_hash=s.content_hash if s.content_hash else None,
                        source_type="news",
                    )
                )

        model_info: ModelInfo | None = None
        if row.model_provider and row.model_name and row.prompt_version:
            failure_code: str | None = None
            for r in row.reasons or []:
                code = r.get("code") if isinstance(r, dict) else getattr(r, "code", None)
                if code in ("MODEL_UNAVAILABLE", "MODEL_OUTPUT_INVALID"):
                    failure_code = code
                    break
            model_info = ModelInfo(
                provider=row.model_provider,
                model=row.model_name,
                prompt_version="research-interpretation-v1",
                failure_code=failure_code,
            )

        data_quality: DataQuality | None = None
        if row.data_quality is not None:
            data_quality = DataQuality.model_validate(row.data_quality)

        return ResearchRun(
            run_id=row.public_id,
            symbol=cast(Any, row.symbol),
            created_at=row.created_at,
            completed_at=row.completed_at,
            as_of=row.as_of,
            workflow_status=WorkflowStatus(row.workflow_status),
            research_status=(
                ResearchStatus(row.research_status) if row.research_status else None
            ),
            summary=row.summary,
            reasons=[Reason.model_validate(r) for r in row.reasons],
            metrics=[ResearchMetric.model_validate(m) for m in row.metrics],
            data_quality=data_quality,
            sources=sources,
            warnings=list(row.warnings or []),
            model_info=model_info,
            versions=VersionInfo(
                response_schema="research-run-response-v1",
                workflow="eod-research-v1",
                metrics="eod-metrics-v1",
                policy="research-policy-v1",
                code=row.code_version,
            ),
            error_code=row.error_code,
            error_message_safe=row.error_message_safe,
        )
