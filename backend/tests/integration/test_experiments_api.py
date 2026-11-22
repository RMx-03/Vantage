"""Experiments HTTP routes: flag gate, auth, ownership, exports (ADR-0008)."""

import csv
import io
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.domain.errors import VantageError
from app.main import app
from app.services.experiments import (
    ExperimentService,
    get_experiment_executor,
    get_experiment_service,
)
from app.services.run_executor import RunExecutor
from tests.integration.test_experiments_service import FakeHistory, NoHistory

pytestmark = pytest.mark.integration

BASE = "/api/v1/experiments"
WAIT = 20.0
SPEC: dict[str, Any] = {
    "question": '=HYPERLINK("http://x")',
    "symbols": ["AAPL", "MSFT"],
    "start": "2022-03-01",
    "end": "2023-12-29",
    "strategy": {"template": "buy_and_hold"},
}


def _headers(user: UUID, verified: bool = True) -> dict[str, str]:
    kind = "verified" if verified else "unverified"
    return {"Authorization": f"Bearer {kind}-{user}"}


def _fake_auth(request: Request) -> AuthenticatedUser:
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    if not token:
        raise VantageError(code="AUTH_REQUIRED", safe_message="Sign in.")
    kind, _, user = token.partition("-")
    return AuthenticatedUser(id=UUID(user), email_verified=kind == "verified")


@pytest.fixture
def executor() -> Iterator[RunExecutor]:
    executor = RunExecutor(1)
    yield executor
    executor.shutdown()


@pytest.fixture
def history() -> FakeHistory:
    return FakeHistory()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, executor: RunExecutor, history: Any
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "RESEARCH_WORKBENCH_ENABLED", True)
    app.dependency_overrides[get_current_user] = _fake_auth
    app.dependency_overrides[get_experiment_service] = lambda: ExperimentService(
        history=history
    )
    app.dependency_overrides[get_experiment_executor] = lambda: executor
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _finished(client: TestClient, executor: RunExecutor, user: UUID) -> str:
    response = client.post(BASE, json=SPEC, headers=_headers(user))
    assert response.status_code == 202, response.text
    assert executor.wait_idle(WAIT)
    return str(response.json()["id"])


ROUTES = [
    ("post", f"{BASE}/plan"),
    ("post", BASE),
    ("get", BASE),
    ("get", f"{BASE}/{uuid4()}"),
    ("post", f"{BASE}/{uuid4()}/replay"),
    ("get", f"{BASE}/{uuid4()}/export"),
    ("delete", f"{BASE}/{uuid4()}"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_every_route_is_404_when_the_flag_is_off(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    monkeypatch.setattr(settings, "RESEARCH_WORKBENCH_ENABLED", False)
    with TestClient(app) as client:
        response = client.request(method, path, json=SPEC)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_every_route_needs_a_session(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    monkeypatch.setattr(settings, "RESEARCH_WORKBENCH_ENABLED", True)
    with TestClient(app) as client:
        response = client.request(method, path, json=SPEC)
    assert response.status_code == 401


def test_unverified_accounts_cannot_start_or_replay(client, make_user) -> None:
    user = make_user("api-exp-unverified")
    headers = _headers(user, verified=False)
    started = client.post(BASE, json=SPEC, headers=headers)
    replayed = client.post(f"{BASE}/{uuid4()}/replay", headers=headers)
    assert (started.status_code, replayed.status_code) == (403, 403)
    assert started.json()["detail"]["code"] == "AUTH_EMAIL_UNVERIFIED"


def test_start_returns_202_with_location_and_finishes(
    client, executor, make_user
) -> None:
    user = make_user("api-exp-start")
    response = client.post(BASE, json=SPEC, headers=_headers(user))
    assert response.status_code == 202
    body = response.json()
    assert response.headers["Location"] == f"{BASE}/{body['id']}"
    assert body["status"] == "running"
    assert executor.wait_idle(WAIT)
    done = client.get(response.headers["Location"], headers=_headers(user))
    assert done.status_code == 200
    assert done.json()["status"] == "succeeded"
    assert done.json()["label"].startswith("Exploratory")
    assert "inputs" not in done.json()


def test_invalid_spec_is_422(client, make_user) -> None:
    bad = {**SPEC, "symbols": []}
    response = client.post(BASE, json=bad, headers=_headers(make_user("api-422")))
    assert response.status_code == 422


@pytest.mark.parametrize("history", [NoHistory()])
def test_plan_calls_no_provider_and_creates_nothing(client, make_user) -> None:
    user = make_user("api-exp-plan")
    response = client.post(f"{BASE}/plan", json=SPEC, headers=_headers(user))
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["sessions"] > 0 and plan["engine_invocations"] == 4
    assert client.get(BASE, headers=_headers(user)).json() == []


def test_foreign_experiments_are_404_on_every_route(
    client, executor, make_user
) -> None:
    owner, other = make_user("api-exp-own"), make_user("api-exp-foreign")
    exp = _finished(client, executor, owner)
    headers = _headers(other)
    responses = [
        client.get(f"{BASE}/{exp}", headers=headers),
        client.post(f"{BASE}/{exp}/replay", headers=headers),
        client.get(f"{BASE}/{exp}/export", headers=headers),
        client.delete(f"{BASE}/{exp}", headers=headers),
    ]
    assert [r.status_code for r in responses] == [404, 404, 404, 404]
    assert client.get(f"{BASE}/{exp}", headers=_headers(owner)).status_code == 200


def test_list_is_newest_first_and_limit_is_1_to_50(client, executor, make_user) -> None:
    user = make_user("api-exp-list")
    first = _finished(client, executor, user)
    second = _finished(client, executor, user)
    headers = _headers(user)
    listed = client.get(BASE, headers=headers).json()
    assert [item["id"] for item in listed] == [second, first]
    assert "result" not in listed[0]
    one = client.get(f"{BASE}?limit=1", headers=headers).json()
    assert [item["id"] for item in one] == [second]
    for bad in (0, 51):
        assert client.get(f"{BASE}?limit={bad}", headers=headers).status_code == 422


def test_replay_returns_202_and_links_the_original(client, executor, make_user) -> None:
    user = make_user("api-exp-replay")
    exp = _finished(client, executor, user)
    response = client.post(f"{BASE}/{exp}/replay", headers=_headers(user))
    assert response.status_code == 202
    body = response.json()
    assert body["replay_of"] == exp
    assert response.headers["Location"] == f"{BASE}/{body['id']}"
    assert executor.wait_idle(WAIT)


def test_json_export_is_derived_data_only(client, executor, make_user) -> None:
    user = make_user("api-exp-json")
    exp = _finished(client, executor, user)
    response = client.get(f"{BASE}/{exp}/export?format=json", headers=_headers(user))
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    body = response.json()
    assert body["result"]["series"]["nav"]
    assert body["versions"]["inputs_hash"]
    assert "inputs" not in body
    for raw in ("open_adj", "close_adj", "dollar_volume"):
        assert raw not in response.text


def test_csv_export_escapes_formula_cells(client, executor, make_user) -> None:
    user = make_user("api-exp-csv")
    exp = _finished(client, executor, user)
    response = client.get(f"{BASE}/{exp}/export?format=csv", headers=_headers(user))
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    assert "attachment" in response.headers["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert set(rows[0]) == {"section", "date", "symbol", "field", "value"}
    question = next(r for r in rows if r["field"] == "question")
    assert question["value"] == "'" + SPEC["question"]
    sections = {r["section"] for r in rows}
    assert {"spec", "metrics", "series", "trade", "version"} <= sections
    nav = [r for r in rows if r["section"] == "series" and r["field"] == "nav"]
    assert nav and float(nav[0]["value"]) > 0
    # Numbers are data, not formulas: negative values stay numeric.
    for row in rows:
        value = row["value"]
        if value and value[0] in "=+-@":
            float(value)
    for raw in ("open_adj", "close_adj", "dollar_volume"):
        assert raw not in response.text


def test_unknown_export_format_is_422(client, executor, make_user) -> None:
    user = make_user("api-exp-fmt")
    exp = _finished(client, executor, user)
    response = client.get(f"{BASE}/{exp}/export?format=xlsx", headers=_headers(user))
    assert response.status_code == 422


def test_delete_frees_the_experiment(client, executor, make_user) -> None:
    user = make_user("api-exp-delete")
    exp = _finished(client, executor, user)
    assert client.delete(f"{BASE}/{exp}", headers=_headers(user)).status_code == 204
    assert client.get(f"{BASE}/{exp}", headers=_headers(user)).status_code == 404


def test_capacity_and_draining_send_retry_after(client, make_user) -> None:
    full = RunExecutor(1)
    slot = full.reserve()
    app.dependency_overrides[get_experiment_executor] = lambda: full
    try:
        busy = client.post(BASE, json=SPEC, headers=_headers(make_user("api-cap")))
    finally:
        slot.release()
    full.begin_drain()
    try:
        draining = client.post(
            BASE, json=SPEC, headers=_headers(make_user("api-drain"))
        )
    finally:
        full.shutdown()
    assert (busy.status_code, draining.status_code) == (429, 503)
    assert busy.headers["Retry-After"] == draining.headers["Retry-After"] == "5"


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2024-03-29", "2024-03-31", "no trading sessions"),
        ("2000-01-03", "2009-12-31", "on or after"),
    ],
)
def test_unusable_dates_are_explained_and_create_nothing(
    client, make_user, start: str, end: str, message: str
) -> None:
    user = make_user(f"api-exp-dates-{start}")
    spec = {**SPEC, "start": start, "end": end}
    for path in (f"{BASE}/plan", BASE):
        response = client.post(path, json=spec, headers=_headers(user))
        assert response.status_code == 400, response.text
        assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
        assert message in response.json()["detail"]["message"]
    assert client.get(BASE, headers=_headers(user)).json() == []
