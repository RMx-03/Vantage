"""Owner-scoped persistence for Research Workbench experiments."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update

from app.db.models import ExperimentRow
from app.db.session import SessionFactory
from app.domain.experiments import (
    ExperimentRecord,
    ExperimentResult,
    ExperimentSpec,
    ExperimentSummary,
)
from app.domain.research import ResearchStatus, WorkflowStatus

_RUNNING = WorkflowStatus.RUNNING.value


def _record(row: ExperimentRow) -> ExperimentRecord:
    return ExperimentRecord(
        id=row.public_id,
        status=WorkflowStatus(row.status),
        research_status=ResearchStatus(row.research_status)
        if row.research_status
        else None,
        error_code=row.error_code,
        error_message=row.error_message_safe,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        spec=ExperimentSpec.model_validate(row.spec),
        spec_hash=row.spec_hash,
        inputs_hash=row.inputs_hash,
        inputs_bytes=row.inputs_bytes,
        result=ExperimentResult.model_validate(row.result) if row.result else None,
        versions=row.versions,
        replay_of=row.replay_of,
    )


class ExperimentRepository:
    def create_running(
        self,
        user_id: UUID,
        spec: ExperimentSpec,
        versions: dict[str, str],
        replay_of: UUID | None = None,
    ) -> ExperimentRecord:
        now = datetime.now(UTC)
        with SessionFactory() as session, session.begin():
            row = ExperimentRow(
                public_id=uuid4(),
                user_id=user_id,
                status=_RUNNING,
                created_at=now,
                started_at=now,
                spec=spec.model_dump(mode="json"),
                spec_hash=spec.spec_hash(),
                inputs_bytes=0,
                versions=versions,
                replay_of=replay_of,
            )
            session.add(row)
            session.flush()
            return _record(row)

    def save_success(
        self,
        public_id: UUID,
        inputs: bytes,
        inputs_hash: str,
        result: ExperimentResult,
        versions: dict[str, str],
    ) -> bool:
        """Store inputs and result, only while the experiment is still running."""
        values: dict[str, Any] = {
            "status": WorkflowStatus.SUCCEEDED.value,
            "research_status": result.research_status.value,
            "completed_at": datetime.now(UTC),
            "inputs": inputs,
            "inputs_hash": inputs_hash,
            "inputs_bytes": len(inputs),
            "result": result.model_dump(mode="json"),
            "versions": versions,
        }
        return self._finish(public_id, values)

    def fail_if_running(
        self, public_id: UUID, error_code: str, error_message: str, now: datetime
    ) -> bool:
        values = {
            "status": WorkflowStatus.FAILED.value,
            "research_status": ResearchStatus.FAILED.value,
            "completed_at": now,
            "error_code": error_code,
            "error_message_safe": error_message,
        }
        return self._finish(public_id, values)

    def _finish(self, public_id: UUID, values: dict[str, Any]) -> bool:
        with SessionFactory() as session, session.begin():
            result = session.execute(
                update(ExperimentRow)
                .where(
                    ExperimentRow.public_id == public_id,
                    ExperimentRow.status == _RUNNING,
                )
                .values(**values)
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def get_owned(self, user_id: UUID, public_id: UUID) -> ExperimentRecord | None:
        with SessionFactory() as session:
            row = session.scalars(
                select(ExperimentRow).where(
                    ExperimentRow.public_id == public_id,
                    ExperimentRow.user_id == user_id,
                )
            ).first()
            return _record(row) if row else None

    def get_inputs_owned(self, user_id: UUID, public_id: UUID) -> bytes | None:
        with SessionFactory() as session:
            return session.scalar(
                select(ExperimentRow.inputs).where(
                    ExperimentRow.public_id == public_id,
                    ExperimentRow.user_id == user_id,
                )
            )

    def list_owned(self, user_id: UUID, limit: int = 20) -> list[ExperimentSummary]:
        capped = min(max(1, limit), 50)
        with SessionFactory() as session:
            rows = session.execute(
                select(
                    ExperimentRow.public_id,
                    ExperimentRow.status,
                    ExperimentRow.research_status,
                    ExperimentRow.created_at,
                    ExperimentRow.spec,
                    ExperimentRow.replay_of,
                )
                .where(ExperimentRow.user_id == user_id)
                .order_by(ExperimentRow.created_at.desc(), ExperimentRow.id.desc())
                .limit(capped)
            ).all()
        summaries = []
        for public_id, status, research_status, created_at, spec, replay_of in rows:
            parsed = ExperimentSpec.model_validate(spec)
            summaries.append(
                ExperimentSummary(
                    id=public_id,
                    status=WorkflowStatus(status),
                    research_status=ResearchStatus(research_status)
                    if research_status
                    else None,
                    created_at=created_at,
                    question=parsed.question,
                    template=parsed.strategy.template,
                    symbols=list(parsed.symbols),
                    start=parsed.start,
                    end=parsed.end,
                    replay_of=replay_of,
                )
            )
        return summaries

    def delete_owned(self, user_id: UUID, public_id: UUID) -> bool:
        with SessionFactory() as session, session.begin():
            result = session.execute(
                delete(ExperimentRow).where(
                    ExperimentRow.public_id == public_id,
                    ExperimentRow.user_id == user_id,
                )
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def count_owned(self, user_id: UUID) -> int:
        return self._count(ExperimentRow.user_id == user_id)

    def running_count_owned(self, user_id: UUID) -> int:
        return self._count(
            ExperimentRow.user_id == user_id, ExperimentRow.status == _RUNNING
        )

    def _count(self, *conditions: Any) -> int:
        with SessionFactory() as session:
            return int(session.scalar(select(func.count()).where(*conditions)) or 0)

    def total_input_bytes(self) -> int:
        with SessionFactory() as session:
            return int(
                session.scalar(
                    select(func.coalesce(func.sum(ExperimentRow.inputs_bytes), 0))
                )
                or 0
            )

    def list_stale_running(self, *, started_before: datetime) -> list[UUID]:
        with SessionFactory() as session:
            return list(
                session.scalars(
                    select(ExperimentRow.public_id)
                    .where(
                        ExperimentRow.status == _RUNNING,
                        ExperimentRow.started_at < started_before,
                    )
                    .order_by(ExperimentRow.id)
                ).all()
            )
