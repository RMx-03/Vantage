"""Experiments table and owner-scoped repository (Research Workbench)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.experiments import ExperimentResult, ExperimentSpec
from app.domain.research import ResearchStatus, WorkflowStatus
from app.repositories.experiments import ExperimentRepository
from tests.integration.test_migration_0005 import _alembic

pytestmark = pytest.mark.integration

SPEC = ExperimentSpec.model_validate(
    {
        "question": "Private question text",
        "symbols": ["AAPL", "MSFT"],
        "start": "2020-01-02",
        "end": "2024-12-31",
        "strategy": {"template": "buy_and_hold"},
    }
)
VERSIONS = {"engine": "backtest-engine-v1", "code_revision": "test"}


def _result() -> ExperimentResult:
    return ExperimentResult(
        research_status=ResearchStatus.INFORMATIONAL,
        engine_version="backtest-engine-v1",
        metrics_version="backtest-metrics-v1",
        result_hash="abc",
    )


def test_create_read_and_finish_are_owner_scoped(make_user) -> None:
    repo = ExperimentRepository()
    owner, other = make_user("exp-owner"), make_user("exp-other")
    created = repo.create_running(owner, SPEC, VERSIONS)
    assert created.status == WorkflowStatus.RUNNING
    assert created.spec == SPEC
    assert created.spec_hash == SPEC.spec_hash()
    assert repo.get_owned(other, created.id) is None
    assert repo.get_inputs_owned(other, created.id) is None

    assert repo.save_success(created.id, b"blob", "h" * 64, _result(), VERSIONS)
    done = repo.get_owned(owner, created.id)
    assert done is not None
    assert done.status == WorkflowStatus.SUCCEEDED
    assert done.research_status == ResearchStatus.INFORMATIONAL
    assert done.inputs_hash == "h" * 64 and done.inputs_bytes == 4
    assert done.result is not None and done.result.result_hash == "abc"
    assert done.completed_at is not None
    assert repo.get_inputs_owned(owner, created.id) == b"blob"
    # A finished experiment cannot be finished again.
    assert not repo.save_success(created.id, b"x", "y", _result(), VERSIONS)
    assert not repo.fail_if_running(created.id, "X", "x", datetime.now(UTC))


def test_failure_counts_list_and_delete(make_user) -> None:
    repo = ExperimentRepository()
    owner, other = make_user("exp-list"), make_user("exp-list-other")
    first = repo.create_running(owner, SPEC, VERSIONS)
    second = repo.create_running(owner, SPEC, VERSIONS, replay_of=first.id)
    repo.create_running(other, SPEC, VERSIONS)
    assert repo.running_count_owned(owner) == 2
    assert repo.fail_if_running(
        first.id, "PROVIDER_FAILED", "Safe message.", datetime.now(UTC)
    )
    failed = repo.get_owned(owner, first.id)
    assert failed is not None and failed.status == WorkflowStatus.FAILED
    assert failed.research_status == ResearchStatus.FAILED
    assert (failed.error_code, failed.error_message) == (
        "PROVIDER_FAILED",
        "Safe message.",
    )

    assert repo.count_owned(owner) == 2
    assert [s.id for s in repo.list_owned(owner, limit=10)] == [second.id, first.id]
    assert repo.list_owned(owner, limit=1)[0].id == second.id
    assert repo.get_owned(owner, second.id).replay_of == first.id  # type: ignore[union-attr]

    assert not repo.delete_owned(other, first.id)
    assert repo.delete_owned(owner, first.id)
    assert repo.get_owned(owner, first.id) is None
    assert repo.get_owned(owner, second.id).replay_of is None  # type: ignore[union-attr]
    assert repo.count_owned(owner) == 1


def test_stale_running_and_storage_total(make_user) -> None:
    repo = ExperimentRepository()
    owner = make_user("exp-stale")
    before = repo.total_input_bytes()
    row = repo.create_running(owner, SPEC, VERSIONS)
    later = datetime.now(UTC) + timedelta(seconds=1)
    assert row.id in repo.list_stale_running(started_before=later)
    assert row.id not in repo.list_stale_running(started_before=row.started_at)
    repo.save_success(row.id, b"12345", "h", _result(), VERSIONS)
    assert repo.total_input_bytes() == before + 5
    assert row.id not in repo.list_stale_running(started_before=later)


def test_unknown_ids_are_none() -> None:
    repo = ExperimentRepository()
    assert repo.get_owned(uuid4(), uuid4()) is None
    assert not repo.delete_owned(uuid4(), uuid4())


def test_0007_downgrade_and_upgrade_round_trip() -> None:
    # Downgrades the shared test database, so the suite must stay serial.
    from sqlalchemy import inspect

    from app.db.session import engine

    try:
        _alembic("downgrade", "20261122_0006")
        assert not inspect(engine).has_table("experiments", schema="vantage_app")
        _alembic("upgrade", "head")
        assert inspect(engine).has_table("experiments", schema="vantage_app")
    finally:
        _alembic("upgrade", "head")
