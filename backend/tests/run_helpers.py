"""Run a research request through the asynchronous path and wait for it."""

from datetime import datetime
from uuid import UUID

from app.domain.research import ResearchRun
from app.services.research_run import ResearchRunService
from app.services.run_executor import RunExecutor


def run_to_completion(
    service: ResearchRunService,
    *,
    user_id: UUID,
    symbol: str,
    now: datetime,
    timeout: float = 30.0,
) -> ResearchRun | None:
    """Start a run like the API does, wait for the worker, return the stored run.

    A failed run is persisted, not raised, so callers assert on the returned run
    (or on the repository) instead of expecting an exception.
    """
    pool = RunExecutor(max_workers=1)
    try:
        started = service.start_async(
            user_id=user_id, symbol=symbol, now=now, executor=pool
        )
        assert pool.wait_idle(timeout), "detached run did not finish"
        return service.repo.get_owned(user_id, started.run_id)
    finally:
        pool.shutdown()
