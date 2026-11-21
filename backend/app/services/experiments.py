"""Research Workbench experiments: start, run off the request, replay, sweep.

Experiments run on their own bounded ``RunExecutor`` (one slot by default) so
they never take capacity from research runs. A dyno restart loses in-flight
work; the read-time sweep then marks it interrupted (ADR-0008).
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.backtest import (
    ENGINE_VERSION,
    ExperimentDataError,
    run_experiment,
    with_hash,
)
from app.backtest.inputs import inputs_hash, pack_inputs, unpack_inputs
from app.backtest.metrics import METRICS_VERSION
from app.backtest.plan import plan_experiment
from app.core.config import settings
from app.domain.errors import VantageError
from app.domain.experiments import (
    ExperimentPlan,
    ExperimentRecord,
    ExperimentSpec,
    ExperimentSummary,
    Finding,
)
from app.domain.research import ResearchStatus, WorkflowStatus
from app.providers.contracts import HistoryProvider
from app.providers.registry import default_registry, history_provider
from app.repositories.experiments import ExperimentRepository
from app.services.run_executor import RunExecutor
from app.services.sessions import latest_completed_xnys_session

logger = logging.getLogger(__name__)

TEMPLATES_VERSION = "backtest-templates-v1"
_UNSET: Any = object()


def _error(code: str, message: str) -> VantageError:
    return VantageError(code=code, safe_message=message)


def _not_found() -> VantageError:
    return _error("NOT_FOUND", "Experiment not found.")


@lru_cache(maxsize=1)
def get_experiment_executor() -> RunExecutor:
    return RunExecutor(settings.EXPERIMENT_EXECUTOR_MAX_WORKERS)


def _configured_history() -> HistoryProvider | None:
    market = default_registry().build("market", settings.MARKET_PROVIDER, settings)
    return history_provider(market)


class ExperimentService:
    def __init__(
        self,
        repo: ExperimentRepository | None = None,
        history: HistoryProvider | None = _UNSET,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repo = repo or ExperimentRepository()
        self.history = _configured_history() if history is _UNSET else history
        self._now = now

    # -- reading -----------------------------------------------------------

    def plan(self, spec: ExperimentSpec) -> ExperimentPlan:
        return plan_experiment(self._resolve_end(spec))

    def get(
        self, user_id: UUID, experiment_id: UUID, executor: RunExecutor
    ) -> ExperimentRecord:
        self.expire_stale(executor)
        record = self.repo.get_owned(user_id, experiment_id)
        if record is None:
            raise _not_found()
        return record

    def list(
        self, user_id: UUID, limit: int, executor: RunExecutor
    ) -> list[ExperimentSummary]:
        self.expire_stale(executor)
        return self.repo.list_owned(user_id, limit)

    def delete(self, user_id: UUID, experiment_id: UUID) -> None:
        if not self.repo.delete_owned(user_id, experiment_id):
            raise _not_found()

    def expire_stale(self, executor: RunExecutor) -> int:
        now = self._now()
        before = now - timedelta(seconds=settings.EXPERIMENT_DEADLINE_SECONDS)
        changed = 0
        for public_id in self.repo.list_stale_running(started_before=before):
            if executor.is_in_flight(public_id):
                code = "EXPERIMENT_DEADLINE_EXCEEDED"
                message = "The experiment did not finish within its time limit."
            else:
                code = "EXPERIMENT_INTERRUPTED"
                message = "The experiment was interrupted by a restart. Run it again."
            changed += self.repo.fail_if_running(public_id, code, message, now)
        return changed

    # -- starting ----------------------------------------------------------

    def start(
        self, user_id: UUID, spec: ExperimentSpec, executor: RunExecutor
    ) -> ExperimentRecord:
        if self.history is None:
            raise _error(
                "PROVIDER_NOT_CONFIGURED",
                "Daily history is not configured for the market data provider.",
            )
        resolved = self._resolve_end(spec)
        self._check_limits(user_id)
        history = self.history
        return self._launch(
            user_id,
            resolved,
            executor,
            replay_of=None,
            work=lambda record: self._execute(record.id, resolved, history),
        )

    def replay(
        self, user_id: UUID, experiment_id: UUID, executor: RunExecutor
    ) -> ExperimentRecord:
        original = self.repo.get_owned(user_id, experiment_id)
        if original is None:
            raise _not_found()
        blob = self.repo.get_inputs_owned(user_id, experiment_id)
        if original.status != WorkflowStatus.SUCCEEDED or blob is None:
            raise _error(
                "EXPERIMENT_NOT_REPLAYABLE",
                "Only a finished experiment with saved inputs can be replayed.",
            )
        self._check_limits(user_id)
        expected = original.result.result_hash if original.result else None
        return self._launch(
            user_id,
            original.spec,
            executor,
            replay_of=original.id,
            work=lambda record: self._execute_replay(
                record.id, original.spec, blob, expected
            ),
        )

    def _launch(
        self,
        user_id: UUID,
        spec: ExperimentSpec,
        executor: RunExecutor,
        *,
        replay_of: UUID | None,
        work: Callable[[ExperimentRecord], None],
    ) -> ExperimentRecord:
        slot = executor.reserve()
        try:
            record = self.repo.create_running(
                user_id, spec, self._base_versions(), replay_of=replay_of
            )
        except BaseException:
            slot.release()
            raise
        slot.launch(record.id, lambda: work(record))
        return record

    def _resolve_end(self, spec: ExperimentSpec) -> ExperimentSpec:
        latest = latest_completed_xnys_session(self._now())
        end: date = spec.end or latest
        if end > latest:
            raise _error(
                "VALIDATION_ERROR", "The end date must be a completed trading session."
            )
        try:
            return ExperimentSpec.model_validate(
                {**spec.model_dump(mode="json"), "end": end.isoformat()}
            )
        except ValidationError:
            raise _error(
                "VALIDATION_ERROR",
                "The dates are invalid: end must follow start, within ten years.",
            ) from None

    def _check_limits(self, user_id: UUID) -> None:
        if self.repo.running_count_owned(user_id):
            raise _error(
                "EXPERIMENT_IN_FLIGHT",
                "An experiment is already running. Wait for it to finish.",
            )
        if self.repo.count_owned(user_id) >= settings.EXPERIMENT_MAX_PER_OWNER:
            raise _error(
                "EXPERIMENT_QUOTA_REACHED",
                "The saved-experiment limit is reached. Delete one to run another.",
            )
        limit = settings.EXPERIMENT_STORAGE_LIMIT_MB * 1024 * 1024
        if self.repo.total_input_bytes() >= limit:
            raise _error(
                "EXPERIMENT_STORAGE_FULL",
                "Experiment storage is full on this instance.",
            )

    @staticmethod
    def _base_versions() -> dict[str, str]:
        return {
            "engine": ENGINE_VERSION,
            "metrics": METRICS_VERSION,
            "templates": TEMPLATES_VERSION,
            "code_revision": settings.CODE_REVISION,
        }

    # -- running (on the executor thread) ----------------------------------

    def _execute(
        self, experiment_id: UUID, spec: ExperimentSpec, history: HistoryProvider
    ) -> None:
        def work() -> None:
            plan = plan_experiment(spec)
            assert spec.end is not None
            inputs = history.fetch_daily_history(
                tuple(spec.symbols),
                spec.benchmark,
                plan.fetch_start,
                spec.end,
                self._now(),
            )
            result = run_experiment(spec, inputs)
            digest = inputs_hash(inputs)
            versions = {
                **self._base_versions(),
                "provider": inputs.provider,
                "adjustment": "all",
                "retrieved_at": inputs.retrieved_at.isoformat(),
                "inputs_hash": digest,
                "spec_hash": spec.spec_hash(),
            }
            self.repo.save_success(
                experiment_id, pack_inputs(inputs), digest, result, versions
            )

        self._guard(experiment_id, work)

    def _execute_replay(
        self,
        experiment_id: UUID,
        spec: ExperimentSpec,
        blob: bytes,
        expected_hash: str | None,
    ) -> None:
        def work() -> None:
            inputs = unpack_inputs(blob)
            result = run_experiment(spec, inputs)
            if expected_hash is not None and result.result_hash != expected_hash:
                result = with_hash(
                    result.model_copy(
                        update={
                            "research_status": ResearchStatus.REVIEW,
                            "findings": [
                                *result.findings,
                                Finding(
                                    code="REPLAY_MISMATCH",
                                    message="Replaying the frozen inputs gave a "
                                    "different result, most likely because the "
                                    "engine version changed.",
                                ),
                            ],
                        }
                    )
                )
            digest = inputs_hash(inputs)
            versions = {
                **self._base_versions(),
                "provider": inputs.provider,
                "adjustment": "all",
                "retrieved_at": inputs.retrieved_at.isoformat(),
                "inputs_hash": digest,
                "spec_hash": spec.spec_hash(),
            }
            self.repo.save_success(experiment_id, blob, digest, result, versions)

        self._guard(experiment_id, work)

    def _guard(self, experiment_id: UUID, work: Callable[[], None]) -> None:
        # Wall-clock time: completed_at must never precede the row's started_at.
        try:
            work()
        except ExperimentDataError as exc:
            self.repo.fail_if_running(
                experiment_id, exc.code, exc.message, datetime.now(UTC)
            )
        except VantageError as exc:
            self.repo.fail_if_running(
                experiment_id, exc.code, exc.safe_message, datetime.now(UTC)
            )
        except Exception:
            logger.exception("experiment failed experiment_id=%s", experiment_id)
            self.repo.fail_if_running(
                experiment_id,
                "EXPERIMENT_FAILED",
                "The simulation could not be completed.",
                datetime.now(UTC),
            )
