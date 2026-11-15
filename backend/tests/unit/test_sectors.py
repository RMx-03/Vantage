"""SIC code to SPDR sector ETF table: pinned cases and structural invariants."""

from __future__ import annotations

import pytest

from app.services import sectors
from app.services.sectors import SECTOR_ETFS, SECTOR_MAP_VERSION, sic_to_sector_etf


@pytest.mark.parametrize(
    ("sic", "etf"),
    [
        ("3571", "XLK"),
        ("7372", "XLK"),
        ("3674", "XLK"),
        ("7370", "XLC"),
        ("7841", "XLC"),
        ("4813", "XLC"),
        ("6021", "XLF"),
        ("6311", "XLF"),
        ("2834", "XLV"),
        ("8062", "XLV"),
        ("2911", "XLE"),
        ("1311", "XLE"),
        ("3721", "XLI"),
        ("4011", "XLI"),
        ("3711", "XLY"),
        ("5961", "XLY"),
        ("5812", "XLY"),
        ("5331", "XLP"),
        ("2080", "XLP"),
        ("4911", "XLU"),
        ("2821", "XLB"),
        ("1040", "XLB"),
        ("6798", "XLRE"),
        (" 3571 ", "XLK"),
        ("6324", "XLV"),
        ("6321", "XLF"),
        ("6331", "XLF"),
        ("7389", None),
        ("7388", "XLI"),
        ("3559", None),
        ("3558", "XLI"),
        ("3560", "XLI"),
        ("4922", "XLE"),
        ("4923", None),
        ("4924", None),
        ("4925", "XLU"),
        ("4949", "XLU"),
        ("7371", "XLK"),
        ("8731", None),
        ("8711", "XLI"),
        ("7990", None),
        ("7999", "XLY"),
        ("4841", "XLC"),
        ("6199", "XLF"),
        ("5912", None),
        ("5911", "XLP"),
        ("5913", "XLP"),
        ("7373", "XLK"),
        ("7374", None),
        ("7375", "XLK"),
        ("7320", None),
        ("7321", "XLI"),
        ("3532", "XLI"),
        ("3533", "XLE"),
        ("3534", "XLI"),
        ("3410", "XLI"),
        ("3411", "XLB"),
        ("3412", "XLI"),
        ("5200", None),
        ("5201", "XLY"),
        ("6220", "XLF"),
        ("6221", None),
        ("6222", "XLF"),
        ("4699", None),
        ("4700", None),
        ("4701", "XLI"),
        ("2669", "XLB"),
        ("2670", None),
        ("2671", "XLB"),
        ("3349", "XLB"),
        ("3350", None),
        ("3351", "XLB"),
        ("3356", "XLB"),
        ("3357", None),
        ("3358", "XLB"),
        ("4400", None),
        ("4401", "XLI"),
        ("4955", "XLI"),
        ("3576", "XLK"),
        ("6512", "XLRE"),
        ("4512", "XLI"),
        ("6770", None),
        ("711", None),
    ],
)
def test_pinned_cases(sic: str, etf: str | None) -> None:
    assert sic_to_sector_etf(sic) == etf


@pytest.mark.parametrize(
    "value", ["9995", "", None, "abc", "35a1", "12", "12345", "-3571", "  "]
)
def test_unmapped_or_invalid_is_none(value: str | None) -> None:
    assert sic_to_sector_etf(value) is None


def test_version_and_etf_set() -> None:
    assert SECTOR_MAP_VERSION == "sic-spdr-v1"
    assert len(set(SECTOR_ETFS)) == 11


def test_every_range_is_well_formed() -> None:
    assert sectors._RANGES
    for low, high, etf in sectors._RANGES:
        assert low <= high
        assert etf in SECTOR_ETFS


def test_ranges_do_not_overlap() -> None:
    ordered = sorted(sectors._RANGES)
    for (_, prev_high, _), (low, _, _) in zip(ordered, ordered[1:], strict=False):
        assert prev_high < low


def test_every_etf_is_used() -> None:
    assert {etf for _, _, etf in sectors._RANGES} == set(SECTOR_ETFS)
