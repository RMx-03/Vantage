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
from app.providers.finnhub import FINNHUB_LIMITER, FinnhubNewsProvider
from app.providers.registry import default_registry

TOKEN = "fh-test-token-QWERTY1234567890"
URL = "https://finnhub.io/api/v1/company-news"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "providers" / "finnhub"
CUTOFF = datetime(2026, 11, 13, 21, 0, tzinfo=UTC)
RETRIEVED = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
PAYLOAD = json.loads((FIXTURES / "company_news.json").read_text())

MESSAGES = {
    "auth": "News provider refused the configured credentials.",
    "rate_limited": "News provider rate limit was reached.",
    "unavailable": "Company news could not be retrieved.",
    "malformed": "Company news could not be retrieved.",
}


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    FINNHUB_LIMITER._calls.clear()


def make_provider(
    transport: httpx.BaseTransport | None = None,
) -> FinnhubNewsProvider:
    return FinnhubNewsProvider(
        TOKEN, timeout_seconds=6.0, transport=transport, sleep=lambda seconds: None
    )


def fetch(provider: FinnhubNewsProvider, limit: int = 10, lookback: int = 3) -> Any:
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

    assert snapshot.provider == "finnhub"
    assert snapshot.symbol == "AAPL"
    assert snapshot.quality is ComponentQuality.FRESH
    assert snapshot.error_code is None
    assert snapshot.retrieved_at == RETRIEVED
    assert snapshot.coverage_start == CUTOFF - timedelta(days=3)
    assert snapshot.coverage_end == CUTOFF
    # 130750004 has an empty headline, 130750005 is before the window.
    assert [i.evidence_id for i in snapshot.items] == [
        "finnhub-130750001",
        "finnhub-130750002",
        "finnhub-130750003",
        "finnhub-130750006",
    ]
    times = [i.event_time for i in snapshot.items]
    assert times == sorted(times, reverse=True)

    first = snapshot.items[0]
    assert first.provider == "finnhub"
    assert first.publisher == "Example Wire"
    assert first.event_time == datetime.fromtimestamp(1794580600, tz=UTC)
    assert first.url == (
        "https://www.example-wire.com/technology/apple-on-device-ai-features-2026-11-13"
    )
    assert first.source_type == "news"
    assert first.retrieved_at == RETRIEVED
    assert first.details == EvidenceDetails(
        providers=["finnhub"], tagged_symbols=["AAPL"]
    )
    assert first.details is not None and first.details.company_specific is None


@respx.mock
def test_related_is_split_stripped_uppercased_and_empty_is_list() -> None:
    route(ok)

    items = by_id(fetch(make_provider()))

    details = items["finnhub-130750002"].details
    assert details is not None and details.tagged_symbols == ["AAPL", "MSFT"]
    details = items["finnhub-130750006"].details
    assert details is not None and details.tagged_symbols == []


@respx.mock
def test_blank_publisher_is_none_and_hashed_as_empty() -> None:
    route(ok)

    item = by_id(fetch(make_provider()))["finnhub-130750006"]

    assert item.publisher is None
    assert item.event_time is not None
    expected = hashlib.sha256(
        f"|{item.title.lower()}|{item.event_time.isoformat()}".encode()
    ).hexdigest()
    assert item.content_hash == expected


@respx.mock
def test_content_hash_uses_lowercased_publisher_title_and_time() -> None:
    route(ok)

    first = fetch(make_provider()).items[0]

    expected = hashlib.sha256(
        f"example wire|{first.title.lower()}|{first.event_time.isoformat()}".encode()
    ).hexdigest()
    assert first.content_hash == expected


@respx.mock
def test_summary_has_html_removed_and_whitespace_collapsed() -> None:
    route(ok)

    items = by_id(fetch(make_provider()))

    summary = items["finnhub-130750002"].summary
    assert summary is not None
    assert "<" not in summary and ">" not in summary
    assert "  " not in summary
    assert summary.startswith("An analyst note discusses the services mix")
    assert items["finnhub-130750003"].summary is None


@respx.mock
def test_summary_is_truncated_to_2000_characters() -> None:
    payload = [{**PAYLOAD[0], "summary": "y" * 4000}]
    route(lambda r: httpx.Response(200, json=payload))

    summary = fetch(make_provider()).items[0].summary

    assert summary is not None and len(summary) == 2000


@respx.mock
def test_limit_truncates_after_ordering() -> None:
    route(ok)

    snapshot = fetch(make_provider(), limit=2)

    assert [i.evidence_id for i in snapshot.items] == [
        "finnhub-130750001",
        "finnhub-130750002",
    ]


@respx.mock
def test_equal_event_times_order_by_evidence_id() -> None:
    stamp = int((CUTOFF - timedelta(days=1)).timestamp())
    payload = [
        {**PAYLOAD[0], "id": 9, "datetime": stamp},
        {**PAYLOAD[1], "id": 3, "datetime": stamp},
    ]
    route(lambda r: httpx.Response(200, json=payload))

    ids = [i.evidence_id for i in fetch(make_provider()).items]

    assert ids == ["finnhub-3", "finnhub-9"]


@respx.mock
def test_window_start_excluded_and_cutoff_included() -> None:
    start = int((CUTOFF - timedelta(days=3)).timestamp())
    end = int(CUTOFF.timestamp())
    payload = [
        {**PAYLOAD[0], "id": 1, "datetime": start},
        {**PAYLOAD[1], "id": 2, "datetime": end},
        {**PAYLOAD[2], "id": 3, "datetime": end + 1},
    ]
    route(lambda r: httpx.Response(200, json=payload))

    ids = [i.evidence_id for i in fetch(make_provider()).items]

    assert ids == ["finnhub-2"]


@respx.mock
def test_request_parameters_use_new_york_dates_and_header_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=PAYLOAD)

    route(handler)
    # 2026-11-13 02:00 UTC is still 2026-11-12 in New York.
    early = datetime(2026, 11, 13, 2, 0, tzinfo=UTC)
    make_provider().fetch_company_news("aapl", early, RETRIEVED, 3, 10)

    assert len(seen) == 1
    request = seen[0]
    params = request.url.params
    assert params["symbol"] == "AAPL"
    assert params["from"] == "2026-11-09"
    assert params["to"] == "2026-11-12"
    assert "token" not in params
    assert "token" not in str(request.url).lower()
    assert request.headers["X-Finnhub-Token"] == TOKEN
    assert TOKEN not in str(request.url)


@respx.mock
def test_empty_list_is_missing_without_error_code() -> None:
    route(lambda r: httpx.Response(200, json=[]))

    snapshot = fetch(make_provider())

    assert snapshot.items == []
    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code is None
    assert snapshot.coverage_start == CUTOFF - timedelta(days=3)
    assert snapshot.coverage_end == CUTOFF


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
    assert calls["n"] == (2 if status in (429, 500) else 1)


@respx.mock
def test_malformed_body_message() -> None:
    route(lambda r: httpx.Response(200, text="not json"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "NEWS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
@pytest.mark.parametrize("body", [{"error": "bad"}, "text", 5, None])
def test_unexpected_json_shape_is_malformed(body: Any) -> None:
    route(lambda r: httpx.Response(200, json=body))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "NEWS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
def test_unreadable_items_are_skipped() -> None:
    payload = [
        "junk",
        {**PAYLOAD[0], "datetime": "soon"},
        {**PAYLOAD[0], "datetime": None},
        {**PAYLOAD[0], "id": None},
        PAYLOAD[1],
    ]
    route(lambda r: httpx.Response(200, json=payload))

    ids = [i.evidence_id for i in fetch(make_provider()).items]

    assert ids == ["finnhub-130750002"]


def _chain_text(error: BaseException | None) -> str:
    parts = []
    while error is not None:
        parts.append(repr(error))
        parts.append(str(error))
        error = error.__cause__ or error.__context__
    return " ".join(parts)


@respx.mock
@pytest.mark.parametrize("status", [401, 429, 500])
def test_token_never_leaks(status: int, caplog: pytest.LogCaptureFixture) -> None:
    route(lambda r: httpx.Response(status, text=TOKEN))
    provider = make_provider()

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(VantageError) as exc:
            fetch(provider)

    for text in (_chain_text(exc.value), repr(provider), caplog.text):
        assert TOKEN not in text


@respx.mock
def test_connect_error_does_not_leak_into_the_chain() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError(f"boom {URL}?k={TOKEN}"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["unavailable"]
    assert TOKEN not in _chain_text(exc.value)
    assert URL not in _chain_text(exc.value)


@respx.mock
def test_news_content_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    route(ok)

    with caplog.at_level(logging.DEBUG):
        fetch(make_provider())

    assert "Apple expands" not in caplog.text
    assert "example-wire.com" not in caplog.text


def test_repr_never_shows_the_token() -> None:
    assert repr(make_provider()) == "FinnhubNewsProvider()"


def test_registry_builds_provider_with_key() -> None:
    settings = Settings(_env_file=None, FINNHUB_API_KEY=TOKEN)

    provider = default_registry().build("news", "finnhub", settings)

    assert isinstance(provider, FinnhubNewsProvider)
    assert provider.name == "finnhub"


def test_registry_returns_none_without_key() -> None:
    settings = Settings(_env_file=None, FINNHUB_API_KEY="")

    assert default_registry().build("news", "finnhub", settings) is None
