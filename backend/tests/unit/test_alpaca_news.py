import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import ComponentQuality, EvidenceDetails, NewsItem
from app.providers.alpaca import ALPACA_LIMITER, AlpacaNewsProvider
from app.providers.registry import default_registry

KEY_ID = "PKTESTKEYID123456"
SECRET = "test-secret-ZXCVBNM987654321"
URL = "https://data.alpaca.markets/v1beta1/news"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "providers" / "alpaca"
CUTOFF = datetime(2026, 11, 13, 21, 0, tzinfo=UTC)
RETRIEVED = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
PAYLOAD = json.loads((FIXTURES / "news.json").read_text())

MESSAGES = {
    "auth": "News provider refused the configured credentials.",
    "rate_limited": "News provider rate limit was reached.",
    "unavailable": "Company news could not be retrieved.",
    "malformed": "Company news could not be retrieved.",
}


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    ALPACA_LIMITER._calls.clear()


def make_provider(
    transport: httpx.BaseTransport | None = None,
) -> AlpacaNewsProvider:
    return AlpacaNewsProvider(
        KEY_ID,
        SECRET,
        timeout_seconds=6.0,
        transport=transport,
        sleep=lambda seconds: None,
    )


def fetch(provider: AlpacaNewsProvider, limit: int = 10, lookback: int = 3) -> Any:
    return provider.fetch_company_news("aapl", CUTOFF, RETRIEVED, lookback, limit)


def route(handler: Callable[[httpx.Request], httpx.Response]) -> respx.Route:
    return respx.get(URL).mock(side_effect=handler)


def ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=PAYLOAD)


def by_id(snapshot: Any) -> dict[str, NewsItem]:
    return {i.evidence_id: i for i in snapshot.items}


@respx.mock
def test_happy_path_filters_window_orders_and_cleans() -> None:
    route(ok)

    snapshot = fetch(make_provider())

    assert snapshot.provider == "alpaca"
    assert snapshot.symbol == "AAPL"
    assert snapshot.quality is ComponentQuality.FRESH
    assert snapshot.error_code is None
    assert snapshot.retrieved_at == RETRIEVED
    assert snapshot.coverage_start == CUTOFF - timedelta(days=3)
    assert snapshot.coverage_end == CUTOFF
    # 41004 has a blank headline, 41005 is before the window.
    assert [i.evidence_id for i in snapshot.items] == [
        "alpaca-41001",
        "alpaca-41002",
        "alpaca-41003",
        "alpaca-41006",
    ]
    times = [i.event_time for i in snapshot.items]
    assert times == sorted(times, reverse=True)

    first = snapshot.items[0]
    assert first.provider == "alpaca"
    assert first.publisher == "example-wire"
    assert first.title.startswith("Apple unveils")
    assert first.event_time == datetime(2026, 11, 13, 14, 32, 10, tzinfo=UTC)
    assert first.url == (
        "https://www.example-wire.com/technology/apple-on-device-ai-features-2026-11-13"
    )
    assert first.source_type == "news"
    assert first.retrieved_at == RETRIEVED
    assert first.details == EvidenceDetails(
        providers=["alpaca"], tagged_symbols=["AAPL"]
    )
    assert first.details is not None and first.details.company_specific is None


@respx.mock
def test_summary_has_html_removed_and_whitespace_collapsed() -> None:
    route(ok)

    items = by_id(fetch(make_provider()))

    summary = items["alpaca-41002"].summary
    assert summary is not None
    assert "<" not in summary and ">" not in summary
    assert "  " not in summary and "\n" not in summary
    assert summary.startswith("A key component supplier said shipments to Apple's")
    assert items["alpaca-41003"].summary is None


@respx.mock
def test_summary_is_truncated_to_2000_characters() -> None:
    payload = {
        "news": [{**PAYLOAD["news"][0], "summary": "x" * 5000}],
        "next_page_token": None,
    }
    route(lambda r: httpx.Response(200, json=payload))

    summary = fetch(make_provider()).items[0].summary

    assert summary is not None and len(summary) == 2000


@respx.mock
def test_symbols_are_uppercased_and_blank_publisher_is_none() -> None:
    route(ok)

    items = by_id(fetch(make_provider()))

    details = items["alpaca-41002"].details
    assert details is not None and details.tagged_symbols == ["AAPL", "TSM"]
    details = items["alpaca-41006"].details
    assert details is not None and details.tagged_symbols == ["AAPL", "MSFT", "NVDA"]
    assert items["alpaca-41003"].publisher is None


@respx.mock
def test_content_hash_uses_lowercased_publisher_title_and_time() -> None:
    route(ok)

    items = by_id(fetch(make_provider()))

    first = items["alpaca-41001"]
    assert first.event_time is not None
    expected = hashlib.sha256(
        f"example-wire|{first.title.lower()}|{first.event_time.isoformat()}".encode()
    ).hexdigest()
    assert first.content_hash == expected
    blank = items["alpaca-41003"]
    assert blank.event_time is not None
    expected_blank = hashlib.sha256(
        f"|{blank.title.lower()}|{blank.event_time.isoformat()}".encode()
    ).hexdigest()
    assert blank.content_hash == expected_blank


@respx.mock
def test_limit_truncates_after_ordering() -> None:
    route(ok)

    snapshot = fetch(make_provider(), limit=2)

    assert [i.evidence_id for i in snapshot.items] == ["alpaca-41001", "alpaca-41002"]


@respx.mock
def test_equal_event_times_order_by_evidence_id() -> None:
    news = [
        {**PAYLOAD["news"][0], "id": 9, "created_at": "2026-11-12T10:00:00Z"},
        {**PAYLOAD["news"][1], "id": 3, "created_at": "2026-11-12T10:00:00Z"},
    ]
    route(lambda r: httpx.Response(200, json={"news": news}))

    ids = [i.evidence_id for i in fetch(make_provider()).items]

    assert ids == ["alpaca-3", "alpaca-9"]


@respx.mock
def test_window_start_excluded_and_cutoff_included() -> None:
    start = CUTOFF - timedelta(days=3)
    news = [
        {**PAYLOAD["news"][0], "id": 1, "created_at": start.isoformat()},
        {**PAYLOAD["news"][1], "id": 2, "created_at": CUTOFF.isoformat()},
        {
            **PAYLOAD["news"][2],
            "id": 3,
            "created_at": (CUTOFF + timedelta(seconds=1)).isoformat(),
        },
    ]
    route(lambda r: httpx.Response(200, json={"news": news}))

    ids = [i.evidence_id for i in fetch(make_provider()).items]

    assert ids == ["alpaca-2"]


@respx.mock
def test_request_parameters_and_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=PAYLOAD)

    route(handler)
    fetch(make_provider())

    assert len(seen) == 1
    request = seen[0]
    params = request.url.params
    assert params["symbols"] == "AAPL"
    assert params["start"] == "2026-11-10T21:00:00Z"
    assert params["end"] == "2026-11-13T21:00:00Z"
    assert params["limit"] == "50"
    assert params["sort"] == "desc"
    assert params["include_content"] == "false"
    assert request.headers["APCA-API-KEY-ID"] == KEY_ID
    assert request.headers["APCA-API-SECRET-KEY"] == SECRET
    assert KEY_ID not in str(request.url)
    assert SECRET not in str(request.url)


@respx.mock
def test_empty_list_is_missing_without_error_code() -> None:
    route(lambda r: httpx.Response(200, json={"news": [], "next_page_token": None}))

    snapshot = fetch(make_provider())

    assert snapshot.items == []
    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code is None
    assert snapshot.coverage_start == CUTOFF - timedelta(days=3)
    assert snapshot.coverage_end == CUTOFF


@respx.mock
def test_null_news_is_missing() -> None:
    route(lambda r: httpx.Response(200, json={"news": None}))

    assert fetch(make_provider()).quality is ComponentQuality.MISSING


@respx.mock
def test_pagination_follows_at_most_two_more_pages() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        n = len(seen)
        item = {**PAYLOAD["news"][0], "id": n, "url": f"https://example.com/{n}"}
        return httpx.Response(200, json={"news": [item], "next_page_token": f"t{n}"})

    route(handler)
    snapshot = fetch(make_provider())

    assert len(seen) == 3
    assert "page_token" not in seen[0].url.params
    assert seen[1].url.params["page_token"] == "t1"
    assert seen[2].url.params["page_token"] == "t2"
    assert len(snapshot.items) == 3


@respx.mock
def test_duplicate_ids_across_pages_are_kept_once() -> None:
    pages = iter(
        [
            {"news": [PAYLOAD["news"][0]], "next_page_token": "t"},
            {"news": [PAYLOAD["news"][0]], "next_page_token": None},
        ]
    )
    route(lambda r: httpx.Response(200, json=next(pages)))

    assert len(fetch(make_provider()).items) == 1


@respx.mock
@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "auth"), (403, "auth"), (429, "rate_limited"), (500, "unavailable")],
)
def test_http_failures_map_to_fixed_messages(status: int, kind: str) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    route(handler)

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "NEWS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES[kind]
    assert exc.value.__cause__ is None
    # 429 and 500 retry once; auth failures do not.
    assert calls["n"] == (2 if status in (429, 500) else 1)


@respx.mock
def test_malformed_body_message() -> None:
    route(lambda r: httpx.Response(200, text="not json"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "NEWS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
@pytest.mark.parametrize(
    "body",
    [[], {"news": "oops"}, {"news": {"a": 1}}, {"news": [], "next_page_token": 5}],
)
def test_unexpected_json_shape_is_malformed(body: Any) -> None:
    route(lambda r: httpx.Response(200, json=body))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "NEWS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
def test_unreadable_items_are_skipped() -> None:
    news = [
        "junk",
        {**PAYLOAD["news"][0], "created_at": "not a time"},
        {**PAYLOAD["news"][0], "id": None},
        PAYLOAD["news"][1],
    ]
    route(lambda r: httpx.Response(200, json={"news": news}))

    ids = [i.evidence_id for i in fetch(make_provider()).items]

    assert ids == ["alpaca-41002"]


def _chain_text(error: BaseException | None) -> str:
    parts = []
    while error is not None:
        parts.append(repr(error))
        parts.append(str(error))
        error = error.__cause__ or error.__context__
    return " ".join(parts)


@respx.mock
@pytest.mark.parametrize("status", [401, 429, 500])
def test_keys_never_leak(status: int, caplog: pytest.LogCaptureFixture) -> None:
    route(lambda r: httpx.Response(status, text=f"{KEY_ID} {SECRET}"))
    provider = make_provider()

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(VantageError) as exc:
            fetch(provider)

    for text in (_chain_text(exc.value), repr(provider), caplog.text):
        assert KEY_ID not in text
        assert SECRET not in text


@respx.mock
def test_connect_error_does_not_leak_into_the_chain() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError(f"boom {URL}?k={SECRET}"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["unavailable"]
    assert SECRET not in _chain_text(exc.value)
    assert URL not in _chain_text(exc.value)


@respx.mock
def test_news_content_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    route(ok)

    with caplog.at_level(logging.DEBUG):
        fetch(make_provider())

    assert "Apple unveils" not in caplog.text
    assert "example-wire.com" not in caplog.text


@respx.mock
def test_one_deadline_covers_every_page() -> None:
    clock = {"now": 1000.0}
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        clock["now"] += 4.0
        item = {
            **PAYLOAD["news"][0],
            "id": calls["n"],
            "url": f"https://example.com/{calls['n']}",
        }
        return httpx.Response(
            200, json={"news": [item], "next_page_token": f"t{calls['n']}"}
        )

    route(handler)
    provider = AlpacaNewsProvider(
        KEY_ID,
        SECRET,
        timeout_seconds=6.0,
        sleep=lambda seconds: None,
    )
    provider._http._clock = lambda: clock["now"]  # noqa: SLF001

    with pytest.raises(VantageError) as exc:
        fetch(provider)

    # Two 4 s pages exhaust the single 6 s budget; a third is never sent.
    assert calls["n"] == 2
    assert exc.value.safe_message == MESSAGES["unavailable"]


def test_repr_never_shows_keys() -> None:
    assert repr(make_provider()) == "AlpacaNewsProvider()"


def test_registry_builds_provider_with_both_keys() -> None:
    settings = Settings(
        _env_file=None, ALPACA_API_KEY_ID=KEY_ID, ALPACA_API_SECRET_KEY=SECRET
    )

    provider = default_registry().build("news", "alpaca", settings)

    assert isinstance(provider, AlpacaNewsProvider)
    assert provider.name == "alpaca"


@pytest.mark.parametrize(("key_id", "secret"), [("", SECRET), (KEY_ID, ""), ("", "")])
def test_registry_returns_none_when_a_key_is_missing(key_id: str, secret: str) -> None:
    settings = Settings(
        _env_file=None, ALPACA_API_KEY_ID=key_id, ALPACA_API_SECRET_KEY=secret
    )

    assert default_registry().build("news", "alpaca", settings) is None


def test_old_runs_without_tagged_symbols_still_validate() -> None:
    # "yfinance" is a provider string in rows stored before it was removed.
    legacy = {
        "evidence_id": "news-abc",
        "provider": "yfinance",
        "title": "Older stored item",
        "retrieved_at": "2026-10-01T12:00:00Z",
        "details": {"providers": ["yfinance"], "company_specific": None},
    }

    item = NewsItem.model_validate(legacy)

    assert item.details is not None
    assert item.details.tagged_symbols == []
