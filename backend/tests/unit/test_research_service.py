from app.services.research_run import get_research_service


def test_get_research_service_reuses_the_stateless_instance() -> None:
    clear = getattr(get_research_service, "cache_clear", None)
    if clear is not None:
        clear()
    try:
        first = get_research_service()
        second = get_research_service()
        assert second is first
    finally:
        clear = getattr(get_research_service, "cache_clear", None)
        if clear is not None:
            clear()


def _service_with(providers, **kwargs):
    from unittest.mock import MagicMock

    from app.repositories.research_runs import (
        ResearchRunRepository,
        RunningResearchRun,
    )
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.services.research_run import ResearchRunService

    now = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
    repo = MagicMock(spec=ResearchRunRepository)
    repo.create_running.return_value = RunningResearchRun(
        id=1,
        public_id=uuid4(),
        user_id=uuid4(),
        symbol="AAPL",
        workflow_status="running",
        created_at=now,
        started_at=now,
    )
    return ResearchRunService(repo=repo, providers=providers, **kwargs), repo, now


def _provider_set(market, news):
    from app.providers.llm import DisabledInterpretationProvider
    from app.providers.registry import ProviderSet

    return ProviderSet(
        market=market,
        news=(news,),
        filings=None,
        fundamentals=None,
        macro=None,
        crosscheck=None,
        llm=DisabledInterpretationProvider(),
        not_configured=("filings", "fundamentals", "macro", "crosscheck"),
    )


def test_unconfigured_market_fails_the_run() -> None:
    import pytest
    from uuid import uuid4

    from app.domain.errors import VantageError

    service, repo, now = _service_with(_provider_set(None, object()))

    with pytest.raises(VantageError) as exc:
        service.create(user_id=uuid4(), symbol="AAPL", now=now)

    assert exc.value.code == "MARKET_DATA_PROVIDER_FAILED"
    assert repo.finalize_failure.call_args.kwargs["error_code"] == (
        "MARKET_DATA_PROVIDER_FAILED"
    )


def test_explicit_providers_override_the_set() -> None:
    from unittest.mock import MagicMock

    market, news = MagicMock(), MagicMock()
    service, _, _ = _service_with(
        _provider_set(MagicMock(), MagicMock()),
        market_provider=market,
        news_provider=news,
    )
    assert service.market is market
    assert service.news is news
