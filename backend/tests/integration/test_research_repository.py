import base64
from datetime import UTC, date, datetime, timedelta
import json
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionFactory
from app.domain.errors import VantageError
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DailyBar,
    DataQuality,
    EvidenceSource,
    MarketSnapshot,
    ModelInfo,
    ModelQuality,
    OverallQuality,
    Reason,
    ResearchMetric,
    ResearchStatus,
    VersionInfo,
    WorkflowStatus,
)
from app.repositories.research_runs import ResearchRunRepository


@pytest.fixture(scope="session")
def check_db_url() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if "vantage_test" not in db_url:
        pytest.fail(f"DATABASE_URL must target 'vantage_test', got: {db_url}")


@pytest.fixture
def repo(check_db_url) -> ResearchRunRepository:
    return ResearchRunRepository()


@pytest.fixture
def user_id() -> UUID:
    return uuid4()


@pytest.fixture
def other_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def versions() -> VersionInfo:
    return VersionInfo(
        response_schema="research-run-response-v1",
        workflow="eod-research-v1",
        metrics="eod-metrics-v1",
        policy="research-policy-v1",
        code="test-commit",
    )


@pytest.fixture
def valid_snapshot() -> tuple[MarketSnapshot, list[EvidenceSource]]:
    now = datetime.now(UTC)
    bars = [
        DailyBar(
            symbol="AAPL",
            session_date=date(2026, 9, 11),
            open=150.0,
            high=155.0,
            low=149.0,
            close=152.0,
            adjusted_close=152.0,
            volume=1_000_000,
            currency="USD",
            provider="fixture",
            retrieved_at=now,
            adjustment_state="split_adjusted",
        )
    ]
    market = MarketSnapshot(
        symbol="AAPL",
        bars=bars,
        provider="fixture",
        retrieved_at=now,
        as_of=now,
        latest_completed_session=date(2026, 9, 11),
        content_hash="a" * 64,
        quality=ComponentQuality.FRESH,
    )
    sources = [
        EvidenceSource(
            evidence_id="ev-1",
            provider="fixture",
            publisher="Reuters",
            title="AAPL earnings update",
            url="https://example.com/news",
            event_time=now,
            retrieved_at=now,
            content_hash="b" * 64,
        )
    ]
    return market, sources


@pytest.fixture
def running_run(repo: ResearchRunRepository, user_id: UUID, versions: VersionInfo):
    return repo.create_running(user_id=user_id, symbol="AAPL", versions=versions)


@pytest.fixture
def completed_run(repo: ResearchRunRepository, user_id: UUID, versions: VersionInfo, valid_snapshot):
    run = repo.create_running(user_id=user_id, symbol="AAPL", versions=versions)
    market, sources = valid_snapshot
    repo.save_snapshot(run.id, market, sources)
    now = datetime.now(UTC)
    quality = DataQuality(
        overall=OverallQuality.SUFFICIENT,
        prices=ComponentQuality.FRESH,
        news=ComponentQuality.FRESH,
        model=ModelQuality.HEALTHY,
    )
    model_info = ModelInfo(
        provider="gemini",
        model="gemini-2.5-flash",
        prompt_version="research-interpretation-v1",
    )
    return repo.finalize_success(
        internal_id=run.id,
        user_id=user_id,
        research_status=ResearchStatus.INFORMATIONAL,
        as_of=now,
        reasons=[],
        metrics=[],
        data_quality=quality,
        warnings=[],
        summary="All good",
        model_info=model_info,
    )


@pytest.fixture
def three_runs(repo: ResearchRunRepository, user_id: UUID, versions: VersionInfo):
    runs = []
    for i in range(3):
        r = repo.create_running(user_id=user_id, symbol=f"SYM{i}", versions=versions)
        runs.append(r)
    return runs


def test_run_is_created_running_before_finalization(
    repo: ResearchRunRepository, user_id: UUID, versions: VersionInfo
) -> None:
    run = repo.create_running(user_id=user_id, symbol="AAPL", versions=versions)
    assert run.workflow_status == "running"
    assert run.public_id is not None
    assert run.symbol == "AAPL"


def test_cross_user_lookup_does_not_disclose_run(
    repo: ResearchRunRepository, user_id: UUID, other_user_id: UUID, completed_run
) -> None:
    assert repo.get_owned(user_id=other_user_id, public_id=completed_run.public_id) is None
    owned = repo.get_owned(user_id=user_id, public_id=completed_run.public_id)
    assert owned is not None
    assert owned.run_id == completed_run.public_id


def test_snapshot_is_unique_per_run(
    repo: ResearchRunRepository, running_run, valid_snapshot
) -> None:
    market, sources = valid_snapshot
    repo.save_snapshot(running_run.id, market, sources)
    with pytest.raises(IntegrityError):
        repo.save_snapshot(running_run.id, market, sources)


def test_history_cursor_is_stable(
    repo: ResearchRunRepository, user_id: UUID, three_runs
) -> None:
    first = repo.list_owned(user_id=user_id, limit=2, before=None)
    assert len(first.items) == 2
    assert first.next_cursor is not None

    second = repo.list_owned(user_id=user_id, limit=2, before=first.next_cursor)
    assert len(second.items) == 1

    all_ids = [r.run_id for r in first.items + second.items]
    # Ordering is desc by created_at, id
    expected_ids = [r.public_id for r in reversed(three_runs)]
    assert all_ids == expected_ids


def test_invalid_cursor_raises_vantage_error(
    repo: ResearchRunRepository, user_id: UUID
) -> None:
    with pytest.raises(VantageError) as exc_info:
        repo.list_owned(user_id=user_id, limit=10, before="not-valid-base64!@#")
    assert exc_info.value.code == "INVALID_CURSOR"


def test_finalize_failure(
    repo: ResearchRunRepository, user_id: UUID, versions: VersionInfo
) -> None:
    run = repo.create_running(user_id=user_id, symbol="MSFT", versions=versions)
    finalized = repo.finalize_failure(
        internal_id=run.id,
        user_id=user_id,
        error_code="MARKET_DATA_PROVIDER_FAILED",
        error_message_safe="Failed to retrieve market prices.",
    )
    assert finalized.workflow_status == WorkflowStatus.FAILED
    assert finalized.error_code == "MARKET_DATA_PROVIDER_FAILED"
    assert finalized.error_message_safe == "Failed to retrieve market prices."
