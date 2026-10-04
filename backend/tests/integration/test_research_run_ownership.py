from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.research import VersionInfo
from app.repositories.research_runs import ResearchRunRepository
from app.repositories.users import UserRepository

pytestmark = pytest.mark.integration

_VERSIONS = VersionInfo(
    response_schema="s", workflow="w", metrics="m", policy="p", code="c"
)


def test_a_run_can_be_created_for_a_real_user(make_user) -> None:
    owner = make_user("own")
    run = ResearchRunRepository().create_running(
        user_id=owner, symbol="AAPL", versions=_VERSIONS
    )
    assert run.user_id == owner


def test_a_run_cannot_be_created_for_an_unknown_user() -> None:
    # Previously this silently succeeded: user_id was an unconstrained
    # UUID. Ownership is now a database invariant.
    with pytest.raises(IntegrityError):
        ResearchRunRepository().create_running(
            user_id=uuid4(), symbol="AAPL", versions=_VERSIONS
        )
