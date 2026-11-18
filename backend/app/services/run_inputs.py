from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from app.domain.research import (
    FilingsSnapshot,
    FundamentalsSnapshot,
    MacroSnapshot,
    PriceCrossCheckSnapshot,
    RoleQuality,
)

OPTIONAL_ROLES = ("filings", "fundamentals", "macro", "crosscheck")


@dataclass(frozen=True)
class RunInputs:
    """The optional data roles of one run, with what happened to each."""

    filings: FilingsSnapshot | None = None
    fundamentals: FundamentalsSnapshot | None = None
    macro: MacroSnapshot | None = None
    crosscheck: PriceCrossCheckSnapshot | None = None
    sector_etf: str | None = None
    # role -> error code, for a configured role whose call failed
    failed: Mapping[str, str] = field(default_factory=dict)
    not_configured: frozenset[str] = frozenset(OPTIONAL_ROLES)

    def __post_init__(self) -> None:
        # Copy and wrap so the caller's dict, or this field, cannot be mutated later.
        object.__setattr__(self, "failed", MappingProxyType(dict(self.failed)))

    def _snapshot(
        self, role: str
    ) -> (
        FilingsSnapshot
        | FundamentalsSnapshot
        | MacroSnapshot
        | PriceCrossCheckSnapshot
        | None
    ):
        snapshots = {
            "filings": self.filings,
            "fundamentals": self.fundamentals,
            "macro": self.macro,
            "crosscheck": self.crosscheck,
        }
        return snapshots.get(role)

    def role_quality(self, role: str) -> RoleQuality:
        if role in self.not_configured:
            return RoleQuality.NOT_CONFIGURED
        if role in self.failed:
            return RoleQuality.FAILED
        snapshot = self._snapshot(role)
        if snapshot is None:
            return RoleQuality.NOT_CONFIGURED
        return RoleQuality(snapshot.quality.value)

    def role_error(self, role: str) -> str | None:
        if role in self.failed:
            return self.failed[role]
        snapshot = self._snapshot(role)
        return snapshot.error_code if snapshot is not None else None
