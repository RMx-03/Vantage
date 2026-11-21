from datetime import UTC, date, datetime

from sqlalchemy import select

from app.core.config import settings
from app.services.data_stage import collect_inputs
from app.services.sessions import latest_completed_xnys_close, trailing_xnys_sessions
from app.services.snapshots import combined_snapshot_hash
from app.db.models import ResearchRunRow, ResearchSnapshotRow
from app.db.session import SessionFactory
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    DataQuality,
    EvidenceSource,
    ModelQuality,
    OverallQuality,
    ResearchMetric,
    ResearchStatus,
    VersionInfo,
    WorkflowStatus,
)
from app.providers.fixture_provider import FixtureProvider
from app.providers.llm import DisabledInterpretationProvider
from app.providers.registry import ProviderSet
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


NOW = datetime(2026, 11, 27, 22, 0, tzinfo=UTC)

RELATIVE_KEYS = (
    "excess_return_5_vs_spy",
    "excess_return_20_vs_spy",
    "excess_return_20_vs_sector",
)
FUNDAMENTALS_KEYS = ("revenue_growth_fy_yoy", "net_margin_fy")
MACRO_KEYS = ("us10y_yield", "fed_funds_rate", "yield_curve_10y_2y", "vix_close")
FILING_KEYS = ("filing_count_30d", "insider_filing_count_90d")


def _provider_set(fixture: FixtureProvider, *, all_roles: bool) -> ProviderSet:
    return ProviderSet(
        market=fixture,
        news=(fixture,),
        filings=fixture if all_roles else None,
        fundamentals=fixture if all_roles else None,
        macro=fixture if all_roles else None,
        crosscheck=None,
        llm=DisabledInterpretationProvider(),
        not_configured=(
            ("crosscheck",)
            if all_roles
            else ("filings", "fundamentals", "macro", "crosscheck")
        ),
    )


def test_all_roles_from_the_fixture_provider(make_user) -> None:
    user_id = make_user("fixture-all")
    repo = ResearchRunRepository()
    service = ResearchRunService(
        repo=repo, providers=_provider_set(FixtureProvider(), all_roles=True)
    )

    run = service.create(user_id=user_id, symbol="AAPL", now=NOW)

    assert run.workflow_status == WorkflowStatus.SUCCEEDED
    assert run.versions.metrics == "eod-metrics-v3"
    assert run.versions.policy == "research-policy-v2"
    assert run.versions.response_schema == "research-run-response-v3"
    assert run.versions.workflow == "eod-research-v1"
    assert run.snapshot is not None
    assert run.snapshot.providers is not None
    assert {p.role for p in run.snapshot.providers} == {
        "market",
        "news",
        "filings",
        "fundamentals",
        "macro",
        "crosscheck",
    }

    types = {s.source_type for s in run.sources}
    assert {"filing", "insider_transaction"} <= types

    metrics = {m.key: m for m in run.metrics}
    for key in (*RELATIVE_KEYS, *FUNDAMENTALS_KEYS, *MACRO_KEYS, *FILING_KEYS):
        assert metrics[key].value is not None, key

    with SessionFactory() as session:
        row = session.scalars(
            select(ResearchSnapshotRow).where(
                ResearchSnapshotRow.public_id == run.snapshot.snapshot_id
            )
        ).one()
        assert row.providers is not None and len(row.providers) == 6
        assert row.context_bars is not None
        assert len(row.context_bars) == 2
        assert "SPY" in row.context_bars
        assert row.fundamentals is not None
        assert row.macro is not None

    reread = repo.get_owned(user_id, run.run_id)
    assert reread is not None
    assert reread.snapshot is not None
    assert reread.snapshot.content_hash == run.snapshot.content_hash
    assert [s.evidence_id for s in reread.sources] == [
        s.evidence_id for s in run.sources
    ]
    for source in reread.sources:
        if source.source_type in ("filing", "insider_transaction"):
            assert source.details is not None
            assert source.details.company_specific is True

    # Rebuild the inputs the run was made from (the fixture is deterministic) and
    # recompute the hash from the read-back sources; a mismatch between the stored
    # hash and the stored evidence would show here.
    sessions = trailing_xnys_sessions(latest_completed_xnys_close(NOW).date())
    collected = collect_inputs(
        _provider_set(FixtureProvider(), all_roles=True),
        symbol="AAPL",
        now=NOW,
        cutoff=latest_completed_xnys_close(NOW),
        sessions=sessions,
        news_lookback_days=settings.NEWS_LOOKBACK_DAYS,
        role_timeout_seconds=float(settings.PROVIDER_TIMEOUT_SECONDS),
        run_id="recompute",
    )
    assert reread.snapshot.content_hash == combined_snapshot_hash(
        collected.market,
        collected.news,
        evidence=reread.sources,
        fundamentals=collected.inputs.fundamentals,
        macro=collected.inputs.macro,
        crosscheck=collected.inputs.crosscheck,
    )


def test_keyless_fixture_run_shows_four_not_configured_reasons(make_user) -> None:
    user_id = make_user("fixture-keyless")
    service = ResearchRunService(
        repo=ResearchRunRepository(),
        providers=_provider_set(FixtureProvider(), all_roles=False),
    )

    run = service.create(user_id=user_id, symbol="AAPL", now=NOW)

    assert run.workflow_status == WorkflowStatus.SUCCEEDED
    assert run.research_status != ResearchStatus.FAILED
    reasons = [r for r in run.reasons if r.code == "PROVIDER_NOT_CONFIGURED"]
    assert len(reasons) == 4
    assert {r.severity for r in reasons} == {"info"}

    metrics = {m.key: m for m in run.metrics}
    for key in (*FUNDAMENTALS_KEYS, *MACRO_KEYS, *FILING_KEYS):
        assert metrics[key].value is None, key
        assert metrics[key].quality == ComponentQuality.MISSING, key
    # Without filings there is no sector ETF.
    assert metrics["excess_return_20_vs_sector"].value is None
    assert metrics["excess_return_20_vs_sector"].quality == ComponentQuality.MISSING


def test_stored_v2_run_still_reads_back(make_user) -> None:
    user_id = make_user("fixture-v2")
    repo = ResearchRunRepository()
    v2 = VersionInfo(
        response_schema="research-run-response-v2",
        workflow="eod-research-v1",
        metrics="eod-metrics-v2",
        policy="research-policy-v1",
        code="old",
    )
    running = repo.create_running(user_id=user_id, symbol="AAPL", versions=v2)
    fixture = FixtureProvider()
    market = fixture.fetch_daily_snapshot(
        "AAPL", date(2026, 10, 29), date(2026, 11, 27), NOW
    )
    news = fixture.fetch_company_news("AAPL", NOW, NOW, 7)
    sources = [
        EvidenceSource(**item.model_dump(exclude={"details"}), details=None)
        for item in news.items
    ]
    repo.save_snapshot(running.id, user_id, market, news, sources)
    repo.finalize_success(
        internal_id=running.id,
        user_id=user_id,
        research_status=ResearchStatus.INFORMATIONAL,
        as_of=NOW,
        reasons=[],
        metrics=[
            ResearchMetric(
                key="return_1_session",
                label="1-session return",
                value=0.01,
                unit="ratio",
                window_sessions=1,
                as_of=NOW,
                calculation_version="eod-metrics-v2",
                quality=ComponentQuality.FRESH,
            )
        ],
        data_quality=DataQuality(
            overall=OverallQuality.SUFFICIENT,
            prices=ComponentQuality.FRESH,
            news=ComponentQuality.FRESH,
            model=ModelQuality.HEALTHY,
        ),
        warnings=[],
        summary="Stored by an earlier version.",
        interpretation=AIInterpretation(
            sentiment_label="neutral",
            summary="Stored without attribution.",
            evidence_ids=[sources[0].evidence_id],
        ),
    )
    with SessionFactory() as session:
        row = session.scalars(
            select(ResearchRunRow).where(ResearchRunRow.id == running.id)
        ).one()
        # A v2 row has no role keys at all, and no attribution key.
        row.data_quality = {
            "overall": "sufficient",
            "prices": "fresh",
            "news": "fresh",
            "model": "healthy",
        }
        row.interpretation = {
            "sentiment_label": "neutral",
            "summary": "Stored without attribution.",
            "evidence_ids": [sources[0].evidence_id],
            "warnings": [],
            "abstained": False,
        }
        session.commit()

    run = repo.get_owned(user_id, running.public_id)

    assert run is not None
    assert run.versions.response_schema == "research-run-response-v2"
    assert run.versions.metrics == "eod-metrics-v2"
    assert run.data_quality is not None
    assert run.data_quality.filings is None
    assert run.data_quality.macro is None
    assert run.data_quality.fundamentals is None
    assert run.data_quality.crosscheck is None
    assert run.snapshot is not None
    assert run.snapshot.providers is None
    assert run.interpretation is not None
    assert run.interpretation.attribution is None
    assert [m.calculation_version for m in run.metrics] == ["eod-metrics-v2"]
    assert run.sources and all(s.details is None for s in run.sources)
