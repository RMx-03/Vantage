import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
import json
import os
from pathlib import Path
from threading import Barrier, current_thread, main_thread
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ResearchRunRow
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
    NewsSnapshot,
    OverallQuality,
    Reason,
    ResearchMetric,
    ResearchRun,
    ResearchStatus,
    SnapshotProvenance,
    VersionInfo,
    WorkflowStatus,
)
import app.repositories.research_runs as research_runs_module
from app.repositories.research_runs import ResearchRunRepository
from app.services.snapshots import combined_snapshot_hash

VALID_INTERPRETATION = AIInterpretation(
    sentiment_label="positive",
    sentiment_score=0.5,
    summary="Coverage supports a constructive read of recent sessions.",
    evidence_ids=["ev-1"],
    warnings=[],
    abstained=False,
    abstention_reason=None,
)


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
def valid_snapshot() -> tuple[MarketSnapshot, NewsSnapshot, list[EvidenceSource]]:
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
    news = NewsSnapshot(
        symbol="AAPL",
        items=sources,
        provider="fixture-news",
        retrieved_at=now,
        coverage_start=now - timedelta(days=1),
        coverage_end=now,
        quality=ComponentQuality.FRESH,
    )
    return market, news, sources


@pytest.fixture
def running_run(repo: ResearchRunRepository, user_id: UUID, versions: VersionInfo):
    return repo.create_running(user_id=user_id, symbol="AAPL", versions=versions)


@pytest.fixture
def completed_run(
    repo: ResearchRunRepository, user_id: UUID, versions: VersionInfo, valid_snapshot
):
    run = repo.create_running(user_id=user_id, symbol="AAPL", versions=versions)
    market, news, sources = valid_snapshot
    repo.save_snapshot(run.id, user_id, market, news, sources)
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
    repo.finalize_success(
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
        interpretation=VALID_INTERPRETATION,
    )
    return run


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
    assert (
        repo.get_owned(user_id=other_user_id, public_id=completed_run.public_id) is None
    )
    owned = repo.get_owned(user_id=user_id, public_id=completed_run.public_id)
    assert owned is not None
    assert owned.run_id == completed_run.public_id


def test_snapshot_is_unique_per_run(
    repo: ResearchRunRepository, running_run, valid_snapshot
) -> None:
    market, news, sources = valid_snapshot
    repo.save_snapshot(running_run.id, running_run.user_id, market, news, sources)
    with pytest.raises(IntegrityError):
        repo.save_snapshot(running_run.id, running_run.user_id, market, news, sources)

    with SessionFactory() as session:
        snapshot_count = session.execute(
            text(
                "SELECT count(*) FROM vantage_app.research_snapshots "
                "WHERE run_id = :run_id"
            ),
            {"run_id": running_run.id},
        ).scalar_one()
        source_count = session.execute(
            text(
                "SELECT count(*) FROM vantage_app.research_sources "
                "WHERE snapshot_id IN "
                "(SELECT id FROM vantage_app.research_snapshots WHERE run_id = :run_id)"
            ),
            {"run_id": running_run.id},
        ).scalar_one()

    assert snapshot_count == 1
    assert source_count == 1


def test_snapshot_write_is_owner_scoped(
    repo: ResearchRunRepository, running_run, other_user_id: UUID, valid_snapshot
) -> None:
    market, news, sources = valid_snapshot
    with pytest.raises(VantageError) as exc_info:
        repo.save_snapshot(running_run.id, other_user_id, market, news, sources)
    assert exc_info.value.code == "RUN_NOT_FOUND"


def test_snapshot_preserves_news_provenance_and_nulls(
    repo: ResearchRunRepository, running_run, valid_snapshot
) -> None:
    market, news, sources = valid_snapshot
    nullable_source = sources[0].model_copy(
        update={
            "publisher": None,
            "url": None,
            "event_time": None,
            "content_hash": None,
        }
    )
    combined_hash = repo.save_snapshot(
        running_run.id,
        running_run.user_id,
        market,
        news.model_copy(update={"items": [nullable_source]}),
        [nullable_source],
    )
    with SessionFactory() as session:
        row = (
            session.execute(
                text(
                    "SELECT market_content_hash, content_hash, news_provider, news_quality "
                    "FROM vantage_app.research_snapshots WHERE run_id = :run_id"
                ),
                {"run_id": running_run.id},
            )
            .mappings()
            .one()
        )
        source = (
            session.execute(
                text(
                    "SELECT publisher, url, event_time, content_hash "
                    "FROM vantage_app.research_sources WHERE snapshot_id = "
                    "(SELECT id FROM vantage_app.research_snapshots WHERE run_id = :run_id)"
                ),
                {"run_id": running_run.id},
            )
            .mappings()
            .one()
        )
    assert row["market_content_hash"] == market.content_hash
    assert row["content_hash"] == combined_hash
    assert row["news_provider"] == "fixture-news"
    assert row["news_quality"] == "fresh"
    assert source == {
        "publisher": None,
        "url": None,
        "event_time": None,
        "content_hash": None,
    }


def test_stored_versions_are_returned_from_the_row(
    repo: ResearchRunRepository, completed_run, user_id: UUID
) -> None:
    with SessionFactory() as session, session.begin():
        session.execute(
            text(
                "UPDATE vantage_app.research_runs SET "
                "response_schema_version='research-run-response-v0', "
                "workflow_version='eod-research-v0', metrics_version='eod-metrics-v0', "
                "policy_version='research-policy-v0', prompt_version='research-interpretation-v0' "
                "WHERE public_id=:public_id"
            ),
            {"public_id": completed_run.run_id},
        )
    stored = repo.get_owned(user_id=user_id, public_id=completed_run.run_id)
    assert stored is not None
    assert stored.versions.model_dump() == {
        "response_schema": "research-run-response-v0",
        "workflow": "eod-research-v0",
        "metrics": "eod-metrics-v0",
        "policy": "research-policy-v0",
        "code": "test-commit",
    }
    assert stored.model_info is not None
    assert stored.model_info.prompt_version == "research-interpretation-v0"


def test_history_cursor_is_stable(
    repo: ResearchRunRepository, user_id: UUID, three_runs
) -> None:
    # Pin created_at explicitly. Clock resolution differs by host -- on a
    # coarse-clock machine three sequential inserts share one created_at and
    # the tiebreaker silently decides the order -- so the direction of the
    # ordering must be asserted against timestamps the test controls.
    oldest, middle, newest = three_runs
    stamps = {
        oldest.public_id: datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        middle.public_id: datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
        newest.public_id: datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
    }
    with SessionFactory() as session, session.begin():
        for public_id, created_at in stamps.items():
            session.execute(
                text(
                    "UPDATE vantage_app.research_runs SET created_at = :created_at "
                    "WHERE public_id = :public_id"
                ),
                {"created_at": created_at, "public_id": public_id},
            )

    first = repo.list_owned(user_id=user_id, limit=2, before=None)
    assert len(first.items) == 2
    assert first.next_cursor is not None

    second = repo.list_owned(user_id=user_id, limit=2, before=first.next_cursor)
    assert len(second.items) == 1

    all_ids = [r.run_id for r in first.items + second.items]
    # History is newest first: a user-visible guarantee, asserted concretely.
    assert all_ids == [newest.public_id, middle.public_id, oldest.public_id]
    assert [r.created_at for r in first.items + second.items] == [
        stamps[newest.public_id],
        stamps[middle.public_id],
        stamps[oldest.public_id],
    ]
    # ...and walking the pages reproduces the unpaged ordering exactly.
    unpaged = repo.list_owned(user_id=user_id, limit=10, before=None)
    assert unpaged.next_cursor is None
    assert all_ids == [r.run_id for r in unpaged.items]


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


def test_terminal_run_cannot_be_overwritten(
    repo: ResearchRunRepository, completed_run, user_id: UUID
) -> None:
    with pytest.raises(VantageError) as exc:
        repo.finalize_failure(
            internal_id=completed_run.id,
            user_id=user_id,
            error_code="INTERNAL_ERROR",
            error_message_safe="Safe failure.",
        )
    assert exc.value.code == "RUN_ALREADY_FINALIZED"


def test_terminal_run_cannot_be_finalized_successfully_twice(
    repo: ResearchRunRepository,
    completed_run,
    user_id: UUID,
) -> None:
    now = datetime.now(UTC)
    quality = DataQuality(
        overall=OverallQuality.SUFFICIENT,
        prices=ComponentQuality.FRESH,
        news=ComponentQuality.FRESH,
        model=ModelQuality.HEALTHY,
    )

    with pytest.raises(VantageError) as exc:
        repo.finalize_success(
            internal_id=completed_run.id,
            user_id=user_id,
            research_status=ResearchStatus.INFORMATIONAL,
            as_of=now,
            reasons=[],
            metrics=[],
            data_quality=quality,
            warnings=[],
            summary="Replacement result",
        )
    assert exc.value.code == "RUN_ALREADY_FINALIZED"


def test_competing_finalizers_allow_exactly_one_terminal_transition(
    repo: ResearchRunRepository,
    running_run,
    user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_select = Barrier(2)
    after_unlocked_select = Barrier(2)

    class CoordinatedSession(Session):
        def scalars(self, statement, *args: Any, **kwargs: Any):
            is_finalizer_select = (
                current_thread() is not main_thread()
                and ResearchRunRow.__table__ in statement.get_final_froms()
            )
            if not is_finalizer_select:
                return super().scalars(statement, *args, **kwargs)

            has_row_lock = getattr(statement, "_for_update_arg", None) is not None
            before_select.wait(timeout=10)
            result = super().scalars(statement, *args, **kwargs)
            if not has_row_lock:
                after_unlocked_select.wait(timeout=10)
            return result

    coordinated_sessions = sessionmaker(
        bind=SessionFactory.kw["bind"],
        expire_on_commit=False,
        autoflush=False,
        class_=CoordinatedSession,
    )
    monkeypatch.setattr(
        research_runs_module,
        "SessionFactory",
        coordinated_sessions,
    )

    quality = DataQuality(
        overall=OverallQuality.SUFFICIENT,
        prices=ComponentQuality.FRESH,
        news=ComponentQuality.FRESH,
        model=ModelQuality.HEALTHY,
    )

    def finalize_success() -> tuple[str, object]:
        try:
            result = repo.finalize_success(
                internal_id=running_run.id,
                user_id=user_id,
                research_status=ResearchStatus.INFORMATIONAL,
                as_of=datetime.now(UTC),
                reasons=[],
                metrics=[],
                data_quality=quality,
                warnings=[],
                summary="Concurrent success",
            )
            return "completed", result
        except VantageError as exc:
            return "error", exc

    def finalize_failure() -> tuple[str, object]:
        try:
            result = repo.finalize_failure(
                internal_id=running_run.id,
                user_id=user_id,
                error_code="INTERNAL_ERROR",
                error_message_safe="Concurrent failure.",
            )
            return "completed", result
        except VantageError as exc:
            return "error", exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [
            future.result(timeout=15)
            for future in (
                executor.submit(finalize_success),
                executor.submit(finalize_failure),
            )
        ]

    completed = [value for kind, value in outcomes if kind == "completed"]
    errors = [value for kind, value in outcomes if kind == "error"]
    assert len(completed) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], VantageError)
    assert errors[0].code == "RUN_ALREADY_FINALIZED"
    assert isinstance(completed[0], ResearchRun)
    winning_run = completed[0]

    stored = repo.get_owned(user_id=user_id, public_id=running_run.public_id)
    assert stored is not None
    assert stored.workflow_status == winning_run.workflow_status
    if stored.workflow_status == WorkflowStatus.SUCCEEDED:
        assert stored.summary == "Concurrent success"
        assert stored.error_code is None
        assert stored.error_message_safe is None
    else:
        assert stored.workflow_status == WorkflowStatus.FAILED
        assert stored.summary is None
        assert stored.error_code == "INTERNAL_ERROR"
        assert stored.error_message_safe == "Concurrent failure."


def test_interpretation_and_provenance_round_trip(
    repo: ResearchRunRepository,
    completed_run,
    user_id: UUID,
    valid_snapshot,
) -> None:
    market, news, _ = valid_snapshot
    with SessionFactory() as session:
        snapshot_public_id = session.execute(
            text(
                "SELECT public_id FROM vantage_app.research_snapshots "
                "WHERE run_id = :run_id"
            ),
            {"run_id": completed_run.id},
        ).scalar_one()

    run = repo.get_owned(user_id=user_id, public_id=completed_run.public_id)

    assert run is not None
    assert run.interpretation == VALID_INTERPRETATION
    assert run.snapshot is not None
    assert run.snapshot.snapshot_id == snapshot_public_id
    assert run.snapshot.content_hash == combined_snapshot_hash(market, news)
    assert set(run.snapshot.model_dump().keys()) == {
        "snapshot_id",
        "content_hash",
        "market_provider",
        "market_content_hash",
        "market_as_of",
        "market_retrieved_at",
        "window_start",
        "window_end",
        "news_provider",
        "news_retrieved_at",
        "news_coverage_start",
        "news_coverage_end",
        "news_quality",
    }
    assert run.snapshot.market_provider == market.provider
    assert run.snapshot.market_content_hash == market.content_hash
    assert run.snapshot.market_as_of == market.as_of
    assert run.snapshot.market_retrieved_at == market.retrieved_at
    assert run.snapshot.window_start <= run.snapshot.window_end
    assert run.snapshot.news_provider == news.provider
    assert run.snapshot.news_retrieved_at == news.retrieved_at
    assert run.snapshot.news_coverage_start == news.coverage_start
    assert run.snapshot.news_coverage_end == news.coverage_end
    assert run.snapshot.news_quality == ComponentQuality.FRESH


def test_absent_interpretation_and_snapshot_map_to_null(
    repo: ResearchRunRepository, running_run, user_id: UUID
) -> None:
    run = repo.get_owned(user_id=user_id, public_id=running_run.public_id)

    assert run is not None
    assert run.versions.response_schema == "research-run-response-v1"
    assert run.interpretation is None
    assert run.snapshot is None


def test_interpretation_is_not_written_to_a_terminal_run(
    repo: ResearchRunRepository, completed_run, user_id: UUID
) -> None:
    replacement = VALID_INTERPRETATION.model_copy(
        update={"summary": "Replacement interpretation"}
    )
    quality = DataQuality(
        overall=OverallQuality.SUFFICIENT,
        prices=ComponentQuality.FRESH,
        news=ComponentQuality.FRESH,
        model=ModelQuality.HEALTHY,
    )

    with pytest.raises(VantageError) as exc:
        repo.finalize_success(
            internal_id=completed_run.id,
            user_id=user_id,
            research_status=ResearchStatus.INFORMATIONAL,
            as_of=datetime.now(UTC),
            reasons=[],
            metrics=[],
            data_quality=quality,
            warnings=[],
            summary="Replacement result",
            interpretation=replacement,
        )

    assert exc.value.code == "RUN_ALREADY_FINALIZED"
    stored = repo.get_owned(user_id=user_id, public_id=completed_run.public_id)
    assert stored is not None
    assert stored.interpretation == VALID_INTERPRETATION


def test_snapshot_provenance_model_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SnapshotProvenance(
            snapshot_id=uuid4(),
            content_hash="a" * 64,
            market_provider="fixture",
            market_content_hash="b" * 64,
            market_as_of=datetime(2026, 9, 11, 20, 0),
            market_retrieved_at=datetime.now(UTC),
            window_start=datetime.now(UTC),
            window_end=datetime.now(UTC),
            news_provider="fixture-news",
            news_retrieved_at=datetime.now(UTC),
            news_coverage_start=None,
            news_coverage_end=None,
            news_quality=ComponentQuality.FRESH,
        )


def test_snapshot_cannot_be_attached_to_a_terminal_run(
    repo: ResearchRunRepository,
    user_id: UUID,
    versions: VersionInfo,
    valid_snapshot,
) -> None:
    run = repo.create_running(user_id=user_id, symbol="MSFT", versions=versions)
    repo.finalize_failure(
        internal_id=run.id,
        user_id=user_id,
        error_code="MARKET_DATA_PROVIDER_FAILED",
        error_message_safe="Failed to retrieve market prices.",
    )
    market, news, sources = valid_snapshot

    with pytest.raises(VantageError) as exc:
        repo.save_snapshot(run.id, user_id, market, news, sources)

    assert exc.value.code == "RUN_ALREADY_FINALIZED"
    with SessionFactory() as session:
        snapshot_count = session.execute(
            text(
                "SELECT count(*) FROM vantage_app.research_snapshots "
                "WHERE run_id = :run_id"
            ),
            {"run_id": run.id},
        ).scalar_one()
    assert snapshot_count == 0


def test_compose_has_no_embedded_runtime_password(project_root: Path) -> None:
    compose = (project_root / "docker-compose.yml").read_text()
    init = (project_root / "backend/docker/postgres/init-runtime-role.sh").read_text()
    assert "vantage_runtime:vantage_runtime" not in compose
    assert "PASSWORD 'vantage_runtime'" not in init
    assert "POSTGRES_RUNTIME_PASSWORD" in compose
    assert "LLM_PROVIDER: ${LLM_PROVIDER:-disabled}" in compose


def test_history_cursor_does_not_expose_internal_row_id(
    repo: ResearchRunRepository, user_id: UUID, three_runs
) -> None:
    """Base64 is encoding, not opacity: a decoded cursor must hold no row counter."""
    page = repo.list_owned(user_id=user_id, limit=2, before=None)
    assert page.next_cursor is not None

    payload = json.loads(
        base64.urlsafe_b64decode(page.next_cursor.encode("utf-8")).decode("utf-8")
    )
    internal_ids = {r.id for r in three_runs}

    assert "id" not in payload
    assert not any(
        isinstance(value, int) and value in internal_ids for value in payload.values()
    )
    assert UUID(str(payload["public_id"])) == page.items[-1].run_id


def test_history_pagination_visits_tied_rows_exactly_once(
    repo: ResearchRunRepository, user_id: UUID, versions: VersionInfo
) -> None:
    """Keyset pagination over rows sharing created_at must not skip or repeat."""
    created = [
        repo.create_running(user_id=user_id, symbol=f"SYM{i}", versions=versions)
        for i in range(7)
    ]
    with SessionFactory() as session, session.begin():
        session.execute(
            text(
                "UPDATE vantage_app.research_runs SET created_at = :created_at "
                "WHERE user_id = :user_id"
            ),
            {
                "created_at": datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
                "user_id": user_id,
            },
        )

    seen: list[UUID] = []
    cursor: str | None = None
    for _ in range(len(created) + 1):
        page = repo.list_owned(user_id=user_id, limit=2, before=cursor)
        seen.extend(item.run_id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert cursor is None
    assert len(seen) == len(created)
    assert set(seen) == {r.public_id for r in created}
    assert seen == sorted(seen, key=lambda run_id: run_id.bytes, reverse=True)


def test_read_path_drops_a_hostile_stored_url(
    repo: ResearchRunRepository, running_run, valid_snapshot, user_id: UUID
) -> None:
    """Historical rows are immutable, so the allowlist runs on the way out."""
    market, news, sources = valid_snapshot
    repo.save_snapshot(running_run.id, user_id, market, news, sources)
    with SessionFactory() as session, session.begin():
        session.execute(
            text(
                "UPDATE vantage_app.research_sources SET url = :url "
                "WHERE snapshot_id = (SELECT id FROM vantage_app.research_snapshots "
                "WHERE run_id = :run_id)"
            ),
            {"url": "javascript:alert(1)", "run_id": running_run.id},
        )

    stored = repo.get_owned(user_id=user_id, public_id=running_run.public_id)

    assert stored is not None
    assert stored.sources
    assert all(s.url is None for s in stored.sources)
    with SessionFactory() as session:
        raw_url = session.execute(
            text(
                "SELECT url FROM vantage_app.research_sources WHERE snapshot_id = "
                "(SELECT id FROM vantage_app.research_snapshots WHERE run_id = :run_id)"
            ),
            {"run_id": running_run.id},
        ).scalar_one()
    assert raw_url == "javascript:alert(1)"


def test_write_and_read_paths_share_one_url_allowlist() -> None:
    """One implementation, so the two boundaries can never drift apart."""
    from app.domain.urls import normalize_url as shared_normalize_url
    import app.providers.yfinance_provider as yfinance_provider

    assert yfinance_provider.normalize_url is shared_normalize_url
    assert research_runs_module.normalize_url is shared_normalize_url
