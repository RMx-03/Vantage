from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import ResearchSnapshotRow
from app.db.session import SessionFactory
from app.domain.research import ComponentQuality, WorkflowStatus
from app.providers.fixture_provider import FixtureProvider
from app.providers.llm import DisabledInterpretationProvider
from app.repositories.research_runs import ResearchRunRepository
from app.services.research_run import ResearchRunService


def test_service_completes_a_run_with_fixture(make_user) -> None:
    user_id = make_user("fixture")
    fixture = FixtureProvider()
    service = ResearchRunService(
        repo=ResearchRunRepository(),
        market_provider=fixture,
        news_provider=fixture,
        interpretation_provider=DisabledInterpretationProvider(),
    )

    run = service.create(
        user_id=user_id,
        symbol="AAPL",
        now=datetime(2026, 11, 27, 22, 0, tzinfo=UTC),
    )

    assert run.workflow_status == WorkflowStatus.SUCCEEDED
    assert run.data_quality is not None
    assert run.data_quality.prices == ComponentQuality.FRESH
    with SessionFactory() as session:
        row = session.scalars(
            select(ResearchSnapshotRow).where(
                ResearchSnapshotRow.market_content_hash
                == run.snapshot.market_content_hash  # type: ignore[union-attr]
            )
        ).first()
        assert row is not None
        assert len(row.price_bars) == 21
