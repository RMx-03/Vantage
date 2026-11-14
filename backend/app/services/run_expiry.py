"""Expire research runs that stayed ``running`` past their deadline.

A module function rather than a service method, so read endpoints can sweep
without building market, news or model providers.
"""

from datetime import datetime, timedelta
from uuid import UUID

from app.core.config import settings
from app.domain.errors import (
    RUN_DEADLINE_EXCEEDED,
    RUN_DEADLINE_EXCEEDED_MESSAGE,
    RUN_INTERRUPTED,
    RUN_INTERRUPTED_MESSAGE,
)
from app.repositories.research_runs import ResearchRunRepository
from app.services.run_executor import RunExecutor


def expire_stale_runs(
    repo: ResearchRunRepository,
    executor: RunExecutor,
    *,
    now: datetime,
    user_id: UUID | None = None,
) -> int:
    """Fail every stale running run and return how many rows changed.

    A run this process is still executing has overrun its deadline; one it is
    not executing lost its worker, normally to a restart. Each update is
    conditional, so a run that finished meanwhile is left untouched.
    """
    started_before = now - timedelta(seconds=settings.RUN_DEADLINE_SECONDS)
    changed = 0
    for public_id in repo.list_stale_running(
        started_before=started_before, user_id=user_id
    ):
        if executor.is_in_flight(public_id):
            code, message = RUN_DEADLINE_EXCEEDED, RUN_DEADLINE_EXCEEDED_MESSAGE
        else:
            code, message = RUN_INTERRUPTED, RUN_INTERRUPTED_MESSAGE
        if repo.fail_if_running(
            public_id=public_id,
            error_code=code,
            error_message_safe=message,
            now=now,
        ):
            changed += 1
    return changed
