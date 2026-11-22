"""Experiments OpenAPI contract, kept apart from the research-run snapshot."""

import json
from pathlib import Path

from app.main import app
from tests.contracts.test_openapi_contract import canonicalize

PATHS = [
    "/api/v1/experiments",
    "/api/v1/experiments/plan",
    "/api/v1/experiments/{experiment_id}",
    "/api/v1/experiments/{experiment_id}/replay",
    "/api/v1/experiments/{experiment_id}/export",
]


def test_experiments_contract_matches_snapshot() -> None:
    snapshot = Path(__file__).parent / "experiments.openapi.json"
    assert snapshot.exists(), f"Snapshot missing: {snapshot}"
    expected = json.loads(snapshot.read_text(encoding="utf-8"))
    assert canonicalize(app.openapi(), paths=PATHS) == expected


def test_every_experiments_route_is_published() -> None:
    published = set(app.openapi()["paths"])
    assert set(PATHS) <= published


def test_research_run_snapshot_reaches_no_experiment_schema() -> None:
    snapshot = Path(__file__).parent / "research-runs.openapi.json"
    schemas = json.loads(snapshot.read_text(encoding="utf-8"))["components"]["schemas"]
    assert not any(name.startswith("Experiment") for name in schemas)
