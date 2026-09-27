import json
from pathlib import Path
from typing import Any
from app.main import app


_REF_PREFIX = "#/components/schemas/"


def _refs_in(node: Any) -> set[str]:
    """Every component schema name referenced anywhere inside `node`."""
    found: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_REF_PREFIX):
            found.add(ref[len(_REF_PREFIX) :])
        for value in node.values():
            found |= _refs_in(value)
    elif isinstance(node, list):
        for value in node:
            found |= _refs_in(value)
    return found


def reachable_schemas(openapi_doc: dict[str, Any], paths: list[str]) -> set[str]:
    """The transitive closure of schemas the given paths reference.

    Derived from the document rather than from the snapshot, so a newly
    referenced schema fails the comparison and a dropped one is noticed.
    """
    all_schemas = openapi_doc.get("components", {}).get("schemas", {})
    frontier = _refs_in([openapi_doc.get("paths", {}).get(p) for p in paths])
    reached: set[str] = set()
    while frontier:
        name = frontier.pop()
        if name in reached or name not in all_schemas:
            continue
        reached.add(name)
        frontier |= _refs_in(all_schemas[name]) - reached
    return reached


def canonicalize(openapi_doc: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    extracted_paths = {
        p: openapi_doc.get("paths", {}).get(p)
        for p in sorted(paths)
        if p in openapi_doc.get("paths", {})
    }
    all_schemas = openapi_doc.get("components", {}).get("schemas", {})
    keep = reachable_schemas(openapi_doc, paths)
    schemas = {k: v for k, v in all_schemas.items() if k in keep}
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
    snapshot_path = Path(__file__).parent / "research-runs.openapi.json"
    assert snapshot_path.exists(), f"Snapshot missing: {snapshot_path}"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
    actual = canonicalize(
        app.openapi(),
        paths=["/api/v1/research-runs", "/api/v1/research-runs/{run_id}"],
    )
    assert actual == expected


def test_research_run_contract_exposes_v2_interpretation_and_provenance() -> None:
    schemas = app.openapi()["components"]["schemas"]

    run_properties = schemas["ResearchRun"]["properties"]
    assert "interpretation" in run_properties
    assert "snapshot" in run_properties
    # Always emitted, so the published contract must match the consumer type.
    assert {"interpretation", "snapshot"} <= set(schemas["ResearchRun"]["required"])

    provenance_properties = schemas["SnapshotProvenance"]["properties"]
    assert set(provenance_properties) == {
        "snapshot_id",
        "content_hash",
        "market_provider",
        "market_content_hash",
        "market_as_of",
        "market_retrieved_at",
        "window_start",
        "window_end",
        "news_provider",
        "news_retrieved_at",
        "news_coverage_start",
        "news_coverage_end",
        "news_quality",
    }


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def test_contract_compares_exactly_the_schemas_the_paths_reach() -> None:
    """The compared schema set must come from the paths, not from the snapshot.

    Filtering by the snapshot's own keys meant a newly referenced schema was
    dropped from the comparison instead of failing it, and its shape was never
    checked; a schema that stopped being referenced was never noticed either.
    """
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {"content": {"application/json": {"schema": _ref("A")}}}
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "A": {"properties": {"b": _ref("B")}},
                "B": {"properties": {"items": {"items": _ref("C")}}},
                "C": {"type": "object"},
                "Unrelated": {"type": "object"},
            }
        },
    }

    result = canonicalize(doc, paths=["/x"])

    assert set(result["components"]["schemas"]) == {"A", "B", "C"}
