from datetime import UTC, datetime

import pytest

from app.domain.research import (
    ComponentQuality,
    FilingsSnapshot,
    RoleQuality,
)
from app.services.run_inputs import OPTIONAL_ROLES, RunInputs


def filings(
    quality: ComponentQuality, error_code: str | None = None
) -> FilingsSnapshot:
    return FilingsSnapshot(
        symbol="AAPL",
        items=[],
        provider="sec-edgar",
        retrieved_at=datetime(2026, 9, 14, tzinfo=UTC),
        quality=quality,
        error_code=error_code,
    )


def test_optional_roles_are_fixed() -> None:
    assert OPTIONAL_ROLES == ("filings", "fundamentals", "macro", "crosscheck")


@pytest.mark.parametrize("role", OPTIONAL_ROLES)
def test_default_inputs_report_every_role_not_configured(role: str) -> None:
    inputs = RunInputs()

    assert inputs.role_quality(role) == RoleQuality.NOT_CONFIGURED
    assert inputs.role_error(role) is None


def test_failed_role_reports_failed_with_its_code() -> None:
    inputs = RunInputs(
        failed={"filings": "PROVIDER_TIMEOUT"},
        not_configured=frozenset({"macro"}),
    )

    assert inputs.role_quality("filings") == RoleQuality.FAILED
    assert inputs.role_error("filings") == "PROVIDER_TIMEOUT"


def test_snapshot_gives_its_own_quality_and_error() -> None:
    inputs = RunInputs(
        filings=filings(ComponentQuality.STALE, "SEC_PARTIAL"),
        not_configured=frozenset(),
    )

    assert inputs.role_quality("filings") == RoleQuality.STALE
    assert inputs.role_error("filings") == "SEC_PARTIAL"


def test_configured_role_with_nothing_is_not_configured() -> None:
    inputs = RunInputs(not_configured=frozenset())

    assert inputs.role_quality("macro") == RoleQuality.NOT_CONFIGURED


def test_role_in_not_configured_wins_over_snapshot() -> None:
    inputs = RunInputs(filings=filings(ComponentQuality.FRESH))

    assert inputs.role_quality("filings") == RoleQuality.NOT_CONFIGURED


def test_failed_mapping_cannot_be_mutated_through_the_dataclass() -> None:
    source = {"macro": "PROVIDER_TIMEOUT"}
    inputs = RunInputs(failed=source, not_configured=frozenset())
    source["filings"] = "X"

    assert "filings" not in inputs.failed
    with pytest.raises(TypeError):
        inputs.failed["filings"] = "X"  # type: ignore[index]
    assert RunInputs().failed == {}
