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
from app.domain.errors import (
    RUN_ALREADY_FINALIZED,
    RUN_ALREADY_FINALIZED_MESSAGE,
    VantageError,
)
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DataQuality,
    EvidenceSource,
    MarketSnapshot,
    ModelInfo,
    ModelQuality,
    NewsSnapshot,
    OverallQuality,
    Reason,
    ResearchMetric,
    ResearchRun,
    ResearchRunPage,
    ResearchStatus,
    SnapshotProvenance,
    VersionInfo,
    WorkflowStatus,
)
from app.domain.urls import safe_stored_url
from app.services.snapshots import combined_snapshot_hash


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
        trace_id: str | None = None,
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
                    policy_version=versions.policy,
                    code_version=versions.code,
                    trace_id=trace_id,
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
        user_id: UUID,
        snapshot: MarketSnapshot,
        news: NewsSnapshot,
        sources: list[EvidenceSource],
    ) -> str:
        with SessionFactory() as session:
            with session.begin():
                run = session.scalars(
                    select(ResearchRunRow)
                    .where(
                        ResearchRunRow.id == internal_id,
                        ResearchRunRow.user_id == user_id,
                    )
                    .with_for_update()
                ).first()
                if run is None:
                    raise VantageError(
                        code="RUN_NOT_FOUND",
                        safe_message="Research run not found.",
                    )
                if run.workflow_status != WorkflowStatus.RUNNING.value:
                    raise VantageError(
                        code=RUN_ALREADY_FINALIZED,
                        safe_message=RUN_ALREADY_FINALIZED_MESSAGE,
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
                    "prices": snapshot.quality.value,
                    "news": news.quality.value,
                }
                content_hash = combined_snapshot_hash(snapshot, news)

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
                    content_hash=content_hash,
                    market_content_hash=snapshot.content_hash,
                    news_provider=news.provider,
                    news_retrieved_at=news.retrieved_at,
                    news_coverage_start=news.coverage_start,
                    news_coverage_end=news.coverage_end,
                    news_quality=news.quality.value,
                    news_error_code=news.error_code,
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
                        publisher=s.publisher,
                        title=s.title,
                        url=s.url,
                        event_time=s.event_time,
                        retrieved_at=s.retrieved_at,
                        content_hash=s.content_hash,
                    )
                    session.add(source_row)
                return content_hash

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
        interpretation: AIInterpretation | None = None,
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
                    .with_for_update()
                )
                row = session.scalars(stmt).first()
                if row is None:
                    raise VantageError(
                        code="RUN_NOT_FOUND",
                        safe_message="Research run not found.",
                    )
                if row.workflow_status != WorkflowStatus.RUNNING.value:
                    raise VantageError(
                        code=RUN_ALREADY_FINALIZED,
                        safe_message=RUN_ALREADY_FINALIZED_MESSAGE,
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
                row.interpretation = (
                    interpretation.model_dump(mode="json")
                    if interpretation is not None
                    else None
                )
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
                    .with_for_update()
                )
                row = session.scalars(stmt).first()
                if row is None:
                    raise VantageError(
                        code="RUN_NOT_FOUND",
                        safe_message="Research run not found.",
                    )
                if row.workflow_status != WorkflowStatus.RUNNING.value:
                    raise VantageError(
                        code=RUN_ALREADY_FINALIZED,
                        safe_message=RUN_ALREADY_FINALIZED_MESSAGE,
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
        cursor_public_id: UUID | None = None
        decoded_created_at: datetime | None = None
        if before is not None:
            try:
                decoded_bytes = base64.urlsafe_b64decode(before.encode("utf-8"))
                payload = json.loads(decoded_bytes.decode("utf-8"))
                decoded_created_at = datetime.fromisoformat(payload["created_at"])
                cursor_public_id = UUID(str(payload["public_id"]))
            except Exception as exc:
                raise VantageError(
                    code="INVALID_CURSOR",
                    safe_message="The history cursor is invalid.",
                ) from exc

        with SessionFactory() as session:
            cursor_filter = None
            if cursor_public_id is not None and decoded_created_at is not None:
                cursor_row = session.execute(
                    select(ResearchRunRow.id, ResearchRunRow.created_at).where(
                        ResearchRunRow.user_id == user_id,
                        ResearchRunRow.public_id == cursor_public_id,
                    )
                ).one_or_none()
                if cursor_row is None or cursor_row.created_at != decoded_created_at:
                    raise VantageError(
                        code="INVALID_CURSOR",
                        safe_message="The history cursor is invalid.",
                    )
                cursor_filter = or_(
                    ResearchRunRow.created_at < cursor_row.created_at,
                    and_(
                        ResearchRunRow.created_at == cursor_row.created_at,
                        ResearchRunRow.id < cursor_row.id,
                    ),
                )

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
            stmt = stmt.order_by(
                ResearchRunRow.created_at.desc(),
                ResearchRunRow.id.desc(),
            ).limit(capped_limit + 1)
            rows = list(session.scalars(stmt).all())

        has_more = len(rows) > capped_limit
        page_rows = rows[:capped_limit]

        next_cursor = None
        if has_more and page_rows:
            last_row = page_rows[-1]
            cursor_payload = json.dumps(
                {
                    "created_at": last_row.created_at.isoformat(),
                    "public_id": str(last_row.public_id),
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
                        # Rows written before the provider gained a scheme
                        # allowlist can still hold a hostile URL. The same
                        # allowlist rejects it on the way out. An accepted URL
                        # is served exactly as stored: the run is immutable and
                        # its published content_hash covers those bytes.
                        url=safe_stored_url(s.url),
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
                code = (
                    r.get("code") if isinstance(r, dict) else getattr(r, "code", None)
                )
                if code in ("MODEL_UNAVAILABLE", "MODEL_OUTPUT_INVALID"):
                    failure_code = code
                    break
            model_info = ModelInfo(
                provider=row.model_provider,
                model=row.model_name,
                prompt_version=row.prompt_version,
                failure_code=failure_code,
            )

        data_quality: DataQuality | None = None
        if row.data_quality is not None:
            data_quality = DataQuality.model_validate(row.data_quality)

        interpretation: AIInterpretation | None = None
        if row.interpretation is not None:
            interpretation = AIInterpretation.model_validate(row.interpretation)

        snapshot: SnapshotProvenance | None = None
        if row.snapshot is not None:
            snapshot = SnapshotProvenance(
                snapshot_id=row.snapshot.public_id,
                content_hash=row.snapshot.content_hash,
                market_provider=row.snapshot.market_provider,
                market_content_hash=row.snapshot.market_content_hash,
                market_as_of=row.snapshot.as_of,
                market_retrieved_at=row.snapshot.retrieved_at,
                window_start=row.snapshot.window_start,
                window_end=row.snapshot.window_end,
                news_provider=row.snapshot.news_provider,
                news_retrieved_at=row.snapshot.news_retrieved_at,
                news_coverage_start=row.snapshot.news_coverage_start,
                news_coverage_end=row.snapshot.news_coverage_end,
                news_quality=ComponentQuality(row.snapshot.news_quality),
            )

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
            interpretation=interpretation,
            snapshot=snapshot,
            versions=VersionInfo(
                response_schema=row.response_schema_version,
                workflow=row.workflow_version,
                metrics=row.metrics_version,
                policy=row.policy_version,
                code=row.code_version,
            ),
            error_code=row.error_code,
            error_message_safe=row.error_message_safe,
        )
