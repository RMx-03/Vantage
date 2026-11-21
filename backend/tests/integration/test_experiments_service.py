"""ExperimentService: start, execute off the request, replay and the stale sweep.

A blocking fake history provider keeps execution deterministic: tests wait on
the executor going idle instead of sleeping.
"""

import threading
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pytest

from app.backtest.inputs import HistoryInputs
from app.core.config import settings
from app.domain.errors import RUN_CAPACITY_EXCEEDED, SERVICE_DRAINING, VantageError
from app.domain.experiments import ExperimentSpec
from app.domain.research import ResearchStatus, WorkflowStatus
from app.providers.fixture_provider import FixtureProvider
from app.repositories.experiments import ExperimentRepository
from app.services.experiments import ExperimentService
from app.services.run_executor import RunExecutor

pytestmark = pytest.mark.integration

NOW = datetime(2024, 1, 5, 22, 0, tzinfo=UTC)
WAIT = 20.0


def _spec(**extra: Any) -> ExperimentSpec:
    raw: dict[str, Any] = {
        "question": "Private question",
        "symbols": ["AAPL", "MSFT"],
        "start": "2022-03-01",
        "end": "2023-12-29",
        "strategy": {"template": "buy_and_hold"},
    }
    raw.update(extra)
    return ExperimentSpec.model_validate(raw)


class FakeHistory:
    name = "fixture"

    def __init__(
        self,
        gate: threading.Event | None = None,
        error: Exception | None = None,
        blank: str | None = None,
    ) -> None:
        self.calls = 0
        self.gate = gate
        self.error = error
        self.blank = blank

    def fetch_daily_history(
        self,
        symbols: tuple[str, ...],
        benchmark: str,
        start: date,
        end: date,
        retrieved_at: datetime,
    ) -> HistoryInputs:
        self.calls += 1
        if self.gate is not None:
            assert self.gate.wait(WAIT)
        if self.error is not None:
            raise self.error
        inputs = FixtureProvider().fetch_daily_history(
            symbols, benchmark, start, end, retrieved_at
        )
        if self.blank in inputs.names:
            j = inputs.names.index(self.blank)
            inputs.close_adj[:, j] = np.nan
        return inputs


class NoHistory:
    name = "none"

    def fetch_daily_history(self, *args: Any, **kwargs: Any) -> HistoryInputs:
        raise AssertionError("replay must not call a provider")


def _service(history: Any, now: datetime = NOW) -> ExperimentService:
    return ExperimentService(history=history, now=lambda: now)


def _finish(executor: RunExecutor) -> None:
    assert executor.wait_idle(WAIT)


def test_start_runs_off_the_request_and_saves_inputs_result_and_versions(
    make_user,
) -> None:
    owner, executor = make_user("svc-ok"), RunExecutor(1)
    history = FakeHistory()
    service = _service(history)
    started = service.start(owner, _spec(), executor)
    assert started.status == WorkflowStatus.RUNNING
    _finish(executor)
    done = service.get(owner, started.id, executor)
    assert done.status == WorkflowStatus.SUCCEEDED, done.error_code
    assert done.result is not None and done.result.metrics is not None
    assert done.inputs_hash and done.inputs_bytes > 0
    assert done.versions["inputs_hash"] == done.inputs_hash
    assert done.versions["provider"] == "fixture"
    assert done.versions["engine"] == "backtest-engine-v1"
    assert history.calls == 1


def test_missing_end_resolves_to_the_latest_completed_session(make_user) -> None:
    owner, executor = make_user("svc-end"), RunExecutor(1)
    raw = _spec().model_dump(mode="json")
    raw["end"] = None
    started = _service(FakeHistory()).start(
        owner, ExperimentSpec.model_validate(raw), executor
    )
    _finish(executor)
    assert started.spec.end == date(2024, 1, 5)


def test_future_end_is_rejected(make_user) -> None:
    with pytest.raises(VantageError) as err:
        _service(FakeHistory()).start(
            make_user("svc-future"), _spec(end="2024-01-08"), RunExecutor(1)
        )
    assert err.value.code == "VALIDATION_ERROR"


def test_one_experiment_in_flight_per_owner(make_user) -> None:
    owner, executor = make_user("svc-flight"), RunExecutor(2)
    gate = threading.Event()
    service = _service(FakeHistory(gate))
    service.start(owner, _spec(), executor)
    try:
        with pytest.raises(VantageError) as err:
            service.start(owner, _spec(), executor)
        assert err.value.code == "EXPERIMENT_IN_FLIGHT"
    finally:
        gate.set()
        _finish(executor)


def test_capacity_and_draining_reuse_the_executor_errors(make_user) -> None:
    executor = RunExecutor(1)
    gate = threading.Event()
    service = _service(FakeHistory(gate))
    service.start(make_user("svc-cap-a"), _spec(), executor)
    try:
        with pytest.raises(VantageError) as err:
            service.start(make_user("svc-cap-b"), _spec(), executor)
        assert err.value.code == RUN_CAPACITY_EXCEEDED
    finally:
        gate.set()
        _finish(executor)
    executor.begin_drain()
    with pytest.raises(VantageError) as err:
        service.start(make_user("svc-drain"), _spec(), executor)
    assert err.value.code == SERVICE_DRAINING


def test_quota_and_storage_are_checked_before_any_fetch(make_user, monkeypatch) -> None:
    owner, executor = make_user("svc-quota"), RunExecutor(1)
    history = FakeHistory()
    service = _service(history)
    service.start(owner, _spec(), executor)
    _finish(executor)
    monkeypatch.setattr(settings, "EXPERIMENT_MAX_PER_OWNER", 1)
    with pytest.raises(VantageError) as err:
        service.start(owner, _spec(), executor)
    assert err.value.code == "EXPERIMENT_QUOTA_REACHED"
    monkeypatch.setattr(settings, "EXPERIMENT_MAX_PER_OWNER", 25)
    monkeypatch.setattr(settings, "EXPERIMENT_STORAGE_LIMIT_MB", 0)
    with pytest.raises(VantageError) as err:
        service.start(make_user("svc-storage"), _spec(), executor)
    assert err.value.code == "EXPERIMENT_STORAGE_FULL"
    assert history.calls == 1


def test_not_configured_history_refuses_without_creating_a_row(make_user) -> None:
    owner = make_user("svc-none")
    with pytest.raises(VantageError) as err:
        _service(None).start(owner, _spec(), RunExecutor(1))
    assert err.value.code == "PROVIDER_NOT_CONFIGURED"
    assert ExperimentRepository().count_owned(owner) == 0


@pytest.mark.parametrize(
    ("history", "code"),
    [
        (
            FakeHistory(
                error=VantageError(
                    code="MARKET_DATA_PROVIDER_FAILED",
                    safe_message="Market prices could not be retrieved.",
                )
            ),
            "MARKET_DATA_PROVIDER_FAILED",
        ),
        (FakeHistory(blank="MSFT"), "SYMBOL_NOT_FOUND"),
        (FakeHistory(error=RuntimeError("boom")), "EXPERIMENT_FAILED"),
    ],
)
def test_failures_are_saved_with_safe_codes(
    make_user, history: FakeHistory, code: str
) -> None:
    owner, executor = make_user("svc-fail"), RunExecutor(1)
    service = _service(history)
    started = service.start(owner, _spec(), executor)
    _finish(executor)
    failed = service.get(owner, started.id, executor)
    assert failed.status == WorkflowStatus.FAILED
    assert failed.research_status == ResearchStatus.FAILED
    assert failed.error_code == code
    assert "boom" not in (failed.error_message or "")


def test_overdue_running_experiment_is_marked_interrupted(make_user) -> None:
    owner = make_user("svc-stale")
    row = ExperimentRepository().create_running(owner, _spec(), {"engine": "x"})
    later = datetime.now(UTC) + timedelta(
        seconds=settings.EXPERIMENT_DEADLINE_SECONDS + 5
    )
    record = _service(FakeHistory(), now=later).get(owner, row.id, RunExecutor(1))
    assert record.status == WorkflowStatus.FAILED
    assert record.error_code == "EXPERIMENT_INTERRUPTED"


def test_replay_reuses_frozen_inputs_and_reproduces_the_hash(make_user) -> None:
    owner, executor = make_user("svc-replay"), RunExecutor(1)
    original = _service(FakeHistory()).start(owner, _spec(), executor)
    _finish(executor)
    service = _service(NoHistory())
    replay = service.replay(owner, original.id, executor)
    assert replay.replay_of == original.id
    _finish(executor)
    first = service.get(owner, original.id, executor)
    again = service.get(owner, replay.id, executor)
    assert again.status == WorkflowStatus.SUCCEEDED, again.error_code
    assert again.inputs_hash == first.inputs_hash
    assert again.result is not None and first.result is not None
    assert again.result.result_hash == first.result.result_hash


def test_foreign_or_unfinished_experiments_cannot_be_replayed(make_user) -> None:
    owner, other, executor = make_user("svc-r1"), make_user("svc-r2"), RunExecutor(1)
    gate = threading.Event()
    service = _service(FakeHistory(gate))
    running = service.start(owner, _spec(), executor)
    try:
        with pytest.raises(VantageError) as err:
            service.replay(other, running.id, executor)
        assert err.value.code == "NOT_FOUND"
    finally:
        gate.set()
        _finish(executor)


def test_delete_is_owner_scoped(make_user) -> None:
    owner, other, executor = make_user("svc-del"), make_user("svc-del2"), RunExecutor(1)
    service = _service(FakeHistory())
    started = service.start(owner, _spec(), executor)
    _finish(executor)
    with pytest.raises(VantageError):
        service.delete(other, started.id)
    service.delete(owner, started.id)
    with pytest.raises(VantageError) as err:
        service.get(owner, started.id, executor)
    assert err.value.code == "NOT_FOUND"


def test_lifespan_drains_the_experiment_executor() -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.experiments import get_experiment_executor

    with TestClient(app):
        executor = get_experiment_executor()
        executor.reserve().release()
    with pytest.raises(VantageError) as err:
        executor.reserve()
    assert err.value.code == SERVICE_DRAINING
