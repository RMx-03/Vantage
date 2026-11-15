import logging

import httpx
import pytest
import respx

from app.domain.errors import VantageError
from app.providers.http import ProviderHttp, ProviderHttpError, RateLimiter, fail

SECRET = "sk-test-SECRET123"
URL = "https://data.example.test/v1/thing"
KINDS = ["auth", "rate_limited", "unavailable", "rejected", "not_found", "malformed"]


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_http(
    t: FakeTime,
    *,
    timeout: float = 6.0,
    max_calls: int = 1000,
    max_wait: float = 2.0,
) -> ProviderHttp:
    limiter = RateLimiter(
        max_calls, 1.0, max_wait_seconds=max_wait, clock=t.clock, sleep=t.sleep
    )
    return ProviderHttp(
        timeout_seconds=timeout,
        limiter=limiter,
        headers={"X-Key": SECRET},
        clock=t.clock,
        sleep=t.sleep,
    )


def trigger(http: ProviderHttp, kind: str) -> ProviderHttpError:
    """Drive one request, carrying the key in a header and a query param."""
    with respx.mock:
        route = respx.get(URL)
        if kind == "auth":
            route.respond(401, text=f"bad key {SECRET}")
        elif kind == "rate_limited":
            route.respond(429, text=SECRET)
        elif kind == "unavailable":
            route.mock(side_effect=httpx.ConnectError(f"failed for {SECRET}"))
        elif kind == "timeout":
            route.mock(side_effect=httpx.ReadTimeout(f"timed out for {SECRET}"))
        elif kind == "rejected":
            route.respond(418, text=SECRET)
        elif kind == "not_found":
            route.respond(404, text=SECRET)
        else:
            route.respond(200, text=f"not json {SECRET}")
        with pytest.raises(ProviderHttpError) as info:
            http.get_json(URL, params={"api_key": SECRET})
    return info.value


@respx.mock
def test_200_json_returns_body() -> None:
    respx.get(URL).respond(200, json={"ok": [1, 2]})
    assert make_http(FakeTime()).get_json(URL) == {"ok": [1, 2]}


@respx.mock
def test_get_text_returns_body() -> None:
    respx.get(URL).respond(200, text="a,b\n1,2")
    assert make_http(FakeTime()).get_text(URL) == "a,b\n1,2"


@respx.mock
def test_503_then_200_retries_once_after_backoff() -> None:
    t = FakeTime()
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )
    assert make_http(t).get_json(URL) == {"ok": True}
    assert route.call_count == 2
    assert t.sleeps == [0.5]


@respx.mock
def test_retry_after_seconds_up_to_two_replaces_backoff() -> None:
    t = FakeTime()
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={}),
        ]
    )
    make_http(t).get_json(URL)
    assert t.sleeps == [1.0]


@respx.mock
def test_503_twice_raises_unavailable() -> None:
    route = respx.get(URL).respond(503)
    with pytest.raises(ProviderHttpError) as info:
        make_http(FakeTime()).get_json(URL)
    assert info.value.kind == "unavailable"
    assert info.value.status == 503
    assert route.call_count == 2


@respx.mock
def test_429_twice_raises_rate_limited() -> None:
    route = respx.get(URL).respond(429)
    with pytest.raises(ProviderHttpError) as info:
        make_http(FakeTime()).get_json(URL)
    assert info.value.kind == "rate_limited"
    assert route.call_count == 2


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
def test_auth_is_not_retried(status: int) -> None:
    route = respx.get(URL).respond(status)
    with pytest.raises(ProviderHttpError) as info:
        make_http(FakeTime()).get_json(URL)
    assert info.value.kind == "auth"
    assert route.call_count == 1


@respx.mock
def test_404_raises_not_found() -> None:
    respx.get(URL).respond(404)
    with pytest.raises(ProviderHttpError) as info:
        make_http(FakeTime()).get_json(URL)
    assert info.value.kind == "not_found"
    assert info.value.status == 404


@respx.mock
def test_418_raises_rejected() -> None:
    respx.get(URL).respond(418)
    with pytest.raises(ProviderHttpError) as info:
        make_http(FakeTime()).get_json(URL)
    assert info.value.kind == "rejected"


@respx.mock
def test_non_json_body_raises_malformed() -> None:
    respx.get(URL).respond(200, text="<html>nope</html>")
    with pytest.raises(ProviderHttpError) as info:
        make_http(FakeTime()).get_json(URL)
    assert info.value.kind == "malformed"
    assert info.value.status == 200


@respx.mock
def test_timeout_with_under_one_second_left_is_not_retried() -> None:
    t = FakeTime()

    def slow_timeout(request: httpx.Request) -> httpx.Response:
        t.now += 1.0  # the attempt consumed 1 s of a 1.5 s budget
        raise httpx.ReadTimeout("slow")

    route = respx.get(URL).mock(side_effect=slow_timeout)
    with pytest.raises(ProviderHttpError) as info:
        make_http(t, timeout=1.5).get_json(URL)
    assert info.value.kind == "unavailable"
    assert info.value.status is None
    assert route.call_count == 1
    assert t.sleeps == []


@respx.mock
def test_each_attempt_uses_remaining_budget_as_timeout() -> None:
    t = FakeTime()
    seen: list[float | None] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"]["read"])
        t.now += 1.0
        return httpx.Response(503)

    respx.get(URL).mock(side_effect=record)
    with pytest.raises(ProviderHttpError):
        make_http(t, timeout=6.0).get_json(URL)
    assert seen == [6.0, 4.5]


def test_limiter_sleeps_when_wait_is_within_cap() -> None:
    t = FakeTime()
    limiter = RateLimiter(2, 1.0, clock=t.clock, sleep=t.sleep)
    limiter.acquire()
    limiter.acquire()
    assert t.sleeps == []
    limiter.acquire()
    assert t.sleeps == [pytest.approx(1.0)]


def test_limiter_raises_when_wait_exceeds_cap() -> None:
    t = FakeTime()
    limiter = RateLimiter(2, 1.0, max_wait_seconds=0, clock=t.clock, sleep=t.sleep)
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(ProviderHttpError) as info:
        limiter.acquire()
    assert info.value.kind == "rate_limited"
    assert t.sleeps == []


@respx.mock
def test_limiter_refusal_sends_no_request() -> None:
    route = respx.get(URL).respond(200, json={})
    http = make_http(FakeTime(), max_calls=1, max_wait=0)
    http.get_json(URL)
    with pytest.raises(ProviderHttpError) as info:
        http.get_json(URL)
    assert info.value.kind == "rate_limited"
    assert route.call_count == 1


@pytest.mark.parametrize("kind", [*KINDS, "timeout"])
def test_errors_never_carry_the_key(
    kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    err = trigger(make_http(FakeTime()), kind)
    assert err.kind == ("unavailable" if kind == "timeout" else kind)
    assert str(err) == err.kind
    assert err.__context__ is None
    assert SECRET not in repr(err.__context__)
    assert SECRET not in str(err)
    assert SECRET not in repr(err)
    assert err.__cause__ is None
    assert SECRET not in caplog.text
    assert "api_key" not in caplog.text
    assert "X-Key" not in caplog.text


@pytest.mark.parametrize("kind", KINDS)
def test_fail_produces_a_safe_vantage_error(
    kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    messages = {k: f"Provider problem: {k}." for k in KINDS}
    provider_err = trigger(make_http(FakeTime()), kind)
    with pytest.raises(VantageError) as info:
        try:
            raise provider_err
        except ProviderHttpError as caught:
            raise fail("PROVIDER_TEST", messages, caught) from None
    e = info.value
    assert e.__context__ is provider_err
    assert provider_err.__context__ is None
    assert SECRET not in repr(e.__context__)
    assert e.code == "PROVIDER_TEST"
    assert e.safe_message == messages[kind]
    assert e.retryable is (kind in {"rate_limited", "unavailable"})
    assert SECRET not in str(e)
    assert SECRET not in repr(e)
    assert e.__cause__ is None
    assert e.__suppress_context__ is True
    assert SECRET not in caplog.text


@respx.mock
def test_deadline_in_the_past_sends_no_request_and_takes_no_slot() -> None:
    t = FakeTime()
    http = make_http(t, max_calls=1)
    route = respx.get(URL).respond(200, json={})
    deadline = http.deadline()
    t.now += 7.0
    with pytest.raises(ProviderHttpError) as info:
        http.get_json(URL, deadline=deadline)
    assert info.value.kind == "unavailable"
    assert info.value.__context__ is None
    assert route.call_count == 0
    # The single limiter slot is still free.
    assert http.get_json(URL) == {}


@respx.mock
def test_attempt_timeout_is_capped_by_the_deadline() -> None:
    t = FakeTime()
    http = make_http(t, timeout=6.0)
    seen: list[float | None] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={})

    respx.get(URL).mock(side_effect=record)
    deadline = http.deadline()
    t.now += 4.0  # an earlier request in the same call used 4 s
    http.get_json(URL, deadline=deadline)
    assert seen == [2.0]


@respx.mock
def test_no_retry_when_under_one_second_remains_against_the_deadline() -> None:
    t = FakeTime()
    http = make_http(t, timeout=6.0)
    route = respx.get(URL).respond(503)
    deadline = t.now + 1.2  # per-request budget alone would allow a retry
    with pytest.raises(ProviderHttpError) as info:
        http.get_json(URL, deadline=deadline)
    assert info.value.kind == "unavailable"
    assert route.call_count == 1
    assert t.sleeps == []
