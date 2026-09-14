import json
from pathlib import Path
from typing import Any
from app.main import app


def canonicalize(openapi_doc: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    extracted_paths = {
        p: openapi_doc.get("paths", {}).get(p)
        for p in sorted(paths)
        if p in openapi_doc.get("paths", {})
    }
    schemas = openapi_doc.get("components", {}).get("schemas", {})
    return {
        "openapi": openapi_doc.get("openapi", "3.1.0"),
        "info": {
            "title": openapi_doc.get("info", {}).get("title"),
            "version": openapi_doc.get("info", {}).get("version"),
        },
        "paths": extracted_paths,
        "components": {
            "schemas": dict(sorted(schemas.items())),
        },
    }


def test_research_run_contract_matches_snapshot() -> None:
    actual = canonicalize(
        app.openapi(),
        paths=["/api/v1/research-runs", "/api/v1/research-runs/{run_id}"],
    )
    snapshot_path = Path(__file__).parent / "research-runs.openapi.json"
    assert snapshot_path.exists(), f"Snapshot missing: {snapshot_path}"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert actual == expected
