import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import ComponentQuality
from app.providers.cache import InMemoryProviderCache
from app.providers.edgar import EDGAR_LIMITER, EdgarProvider
from app.providers.registry import default_registry

AGENT = "Vantage Test Suite sec-contact-7731@example.invalid"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/320193/"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "providers" / "edgar"
CUTOFF = datetime(2026, 11, 13, 21, 0, tzinfo=UTC)
RETRIEVED = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
CUTOFF_DATE = date(2026, 11, 13)
TICKERS = json.loads((FIXTURES / "company_tickers.json").read_text())
SUBMISSIONS = json.loads((FIXTURES / "submissions_aapl.json").read_text())
FORM4 = (FIXTURES / "form4_parsed.xml").read_text()
FORM4_BAD = (FIXTURES / "form4_malformed.xml").read_text()
BAD_ACCESSION = "0001959173-26-000003"
FORM4_URL = re.escape(ARCHIVE) + r".*"

MESSAGES = {
    "auth": "SEC EDGAR refused the request; check SEC_USER_AGENT.",
    "rate_limited": "SEC EDGAR rate limit was reached.",
    "unavailable": "SEC filings could not be retrieved.",
    "malformed": "SEC filings could not be retrieved.",
}


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    EDGAR_LIMITER._calls.clear()


def make_provider(cache: Any = None) -> EdgarProvider:
    return EdgarProvider(
        AGENT,
        cache if cache is not None else InMemoryProviderCache(),
        timeout_seconds=6.0,
        sleep=lambda seconds: None,
    )


def fetch(provider: EdgarProvider, symbol: str = "aapl", lookback: int = 30) -> Any:
    return provider.fetch_filing_evidence(symbol, CUTOFF, RETRIEVED, lookback)


def form4_handler(request: httpx.Request) -> httpx.Response:
    if BAD_ACCESSION.replace("-", "") in str(request.url):
        return httpx.Response(200, text=FORM4_BAD)
    return httpx.Response(200, text=FORM4)


class Mocks:
    def __init__(self) -> None:
        self.tickers = respx.get(TICKERS_URL).mock(
            return_value=httpx.Response(200, json=TICKERS)
        )
        self.submissions = respx.get(SUBMISSIONS_URL).mock(
            return_value=httpx.Response(200, json=SUBMISSIONS)
        )
        self.form4 = respx.get(url__regex=FORM4_URL).mock(side_effect=form4_handler)


def by_id(snapshot: Any) -> dict[str, Any]:
    return {i.evidence_id: i for i in snapshot.items}


def insiders_of(snapshot: Any) -> list[Any]:
    return [i for i in snapshot.items if i.source_type == "insider_transaction"]


@respx.mock
def test_happy_path() -> None:
    mocks = Mocks()

    snapshot = fetch(make_provider())

    assert snapshot.provider == "edgar"
    assert snapshot.symbol == "AAPL"
    assert snapshot.quality is ComponentQuality.FRESH
    assert snapshot.error_code is None
    assert snapshot.cik == "0000320193"
    assert snapshot.company_name == "Apple Inc."
    assert snapshot.sic_code == "3571"
    assert snapshot.retrieved_at == RETRIEVED
    assert snapshot.coverage_start == CUTOFF - timedelta(days=90)
    assert snapshot.coverage_end == CUTOFF
    assert snapshot.insider_filing_count == 12

    items = by_id(snapshot)
    assert "sec-0000320193-26-000121" not in items  # accepted after the cutoff
    assert "sec-0000320193-26-000104" not in items  # 10-Q outside 30 days
    assert "sec-0000320193-25-000079" not in items
    assert "sec-0001308179-26-000101" not in items  # DEF 14A is not used
    filing = items["sec-0000320193-26-000113"]
    assert filing.title == "Form 8-K (Items 2.02, 9.01)"
    assert filing.provider == "edgar"
    assert filing.publisher == "SEC EDGAR"
    assert filing.source_type == "filing"
    assert filing.url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019326000113/0000320193-26-000113-index.htm"
    )
    assert filing.event_time == datetime(2026, 10, 30, 18, 0, tzinfo=UTC)
    assert filing.retrieved_at == RETRIEVED
    assert filing.details is not None
    assert filing.details.providers == ["edgar"]
    assert filing.details.form_type == "8-K"
    assert filing.details.item_codes == ["2.02", "9.01"]

    insiders = insiders_of(snapshot)
    assert len(insiders) == 12
    states = [i.details.parse_state for i in insiders]
    assert states.count("not_fetched") == 2
    assert states.count("parsed") == 9
    assert states.count("unparsed") == 1
    assert len(mocks.form4.calls) == 10
    times = [i.event_time for i in snapshot.items]
    assert times == sorted(times, reverse=True)
    assert len(mocks.tickers.calls) == 1
    assert len(mocks.submissions.calls) == 1


@respx.mock
def test_insider_item_fields() -> None:
    Mocks()

    items = by_id(fetch(make_provider()))

    parsed = items["sec-0001959173-26-000002"]
    assert parsed.title == "Form 4: Example Officer (S)"
    assert parsed.source_type == "insider_transaction"
    assert parsed.details.form_type == "4"
    assert parsed.details.transaction_code == "S"
    assert parsed.details.direction == "disposed"
    assert parsed.details.parse_state == "parsed"
    assert items["sec-0001959173-26-000001"].details.form_type == "4/A"
    skipped = items["sec-0001959173-26-000011"]
    assert skipped.title == "Form 4"
    assert skipped.details.parse_state == "not_fetched"
    assert skipped.details.transaction_code is None
    assert skipped.details.direction is None


@respx.mock
def test_ninety_day_insider_filing_is_excluded() -> None:
    Mocks()

    assert "sec-0001959173-26-000099" not in by_id(fetch(make_provider()))


@respx.mock
def test_form4_document_url_drops_the_xsl_prefix() -> None:
    mocks = Mocks()

    fetch(make_provider())

    urls = {str(c.request.url) for c in mocks.form4.calls}
    assert ARCHIVE + "000195917326000001/wk-form4_1760000000.xml" in urls
    assert not any("xslF345X" in u for u in urls)


@respx.mock
def test_longer_lookback_includes_the_quarterly_report() -> None:
    Mocks()

    items = by_id(fetch(make_provider(), lookback=60))

    assert items["sec-0000320193-26-000104"].title == "Form 10-Q"
    assert items["sec-0000320193-26-000104"].details.item_codes == []


@respx.mock
def test_class_b_ticker_looks_up_with_a_dash() -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, json=TICKERS))
    sub = respx.get("https://data.sec.gov/submissions/CIK0001067983.json").mock(
        return_value=httpx.Response(
            200, json={"name": "BERKSHIRE HATHAWAY INC", "sic": "6331", "filings": {}}
        )
    )

    snapshot = fetch(make_provider(), "BRK.B")

    assert sub.called
    assert snapshot.cik == "0001067983"
    assert snapshot.items == []
    assert snapshot.quality is ComponentQuality.FRESH


@respx.mock
def test_ticker_miss_is_missing_without_a_submissions_request() -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, json=TICKERS))
    sub = respx.get(SUBMISSIONS_URL).mock(return_value=httpx.Response(200, json={}))

    snapshot = fetch(make_provider(), "ZZZZ")

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "NO_SEC_FILER_RECORD"
    assert snapshot.items == []
    assert not sub.called


@respx.mock
def test_submissions_not_found_is_no_filer_record() -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, json=TICKERS))
    respx.get(SUBMISSIONS_URL).mock(return_value=httpx.Response(404))

    snapshot = fetch(make_provider())

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "NO_SEC_FILER_RECORD"


@respx.mock
def test_malformed_form4_is_unparsed_but_present() -> None:
    Mocks()

    item = by_id(fetch(make_provider()))[f"sec-{BAD_ACCESSION}"]

    assert item.details.parse_state == "unparsed"
    assert item.title == "Form 4"
    assert item.source_type == "insider_transaction"


@respx.mock
def test_failed_form4_fetch_is_unparsed_and_not_cached() -> None:
    Mocks()
    respx.get(url__regex=FORM4_URL).mock(return_value=httpx.Response(500))
    cache = InMemoryProviderCache()

    snapshot = fetch(make_provider(cache))

    states = [i.details.parse_state for i in insiders_of(snapshot)]
    assert states.count("unparsed") == 10
    assert states.count("not_fetched") == 2
    assert cache.get("edgar", "form4:0001959173-26-000001", date(2026, 11, 11)) is None


@respx.mock
def test_entity_expansion_is_refused() -> None:
    Mocks()
    evil = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]>'
        "<ownershipDocument>&a;</ownershipDocument>"
    )
    respx.get(url__regex=FORM4_URL).mock(return_value=httpx.Response(200, text=evil))

    snapshot = fetch(make_provider())

    states = [i.details.parse_state for i in insiders_of(snapshot)]
    assert states.count("unparsed") == 10


@respx.mock
def test_second_call_uses_the_cache() -> None:
    mocks = Mocks()
    provider = make_provider(InMemoryProviderCache())

    first = fetch(provider)
    second = fetch(provider)

    assert len(mocks.tickers.calls) == 1
    assert len(mocks.submissions.calls) == 1
    assert len(mocks.form4.calls) == 10  # parsed and unparsed results are cached
    assert [i.model_dump() for i in first.items] == [
        i.model_dump() for i in second.items
    ]


@respx.mock
def test_cache_keys_and_reduced_payloads() -> None:
    Mocks()
    puts: list[tuple[str, str, date, Any, bool]] = []

    class Recording(InMemoryProviderCache):
        def put(  # type: ignore[no-untyped-def]
            self,
            provider,
            cache_key,
            valid_for_date,
            payload,
            retrieved_at,
            *,
            immutable=False,
        ):
            puts.append((provider, cache_key, valid_for_date, payload, immutable))
            return super().put(
                provider,
                cache_key,
                valid_for_date,
                payload,
                retrieved_at,
                immutable=immutable,
            )

    fetch(make_provider(Recording()))

    by_key = {p[1]: p for p in puts}
    tickers = by_key["company_tickers"]
    assert tickers[0] == "edgar" and tickers[2] == CUTOFF_DATE and not tickers[4]
    assert tickers[3]["AAPL"] == [320193, "Apple Inc."]
    assert tickers[3]["BRK-B"] == [1067983, "BERKSHIRE HATHAWAY INC"]
    subs = by_key["submissions:320193"]
    assert subs[2] == CUTOFF_DATE and not subs[4]
    assert set(subs[3]) == {"name", "sic", "filings"}
    assert subs[3]["sic"] == "3571"
    kept = {r["accessionNumber"] for r in subs[3]["filings"]}
    assert "0000320193-24-000123" not in kept  # older than 400 days
    assert "0001308179-26-000101" not in kept  # unused form
    assert "0000320193-25-000079" in kept
    assert set(subs[3]["filings"][0]) == {
        "accessionNumber",
        "filingDate",
        "acceptanceDateTime",
        "form",
        "items",
        "primaryDocument",
    }
    assert len([k for k in by_key if k.startswith("form4:")]) == 10
    one = by_key["form4:0001959173-26-000001"]
    assert one[2] == date(2026, 11, 11) and one[4] is True
    assert one[3]["state"] == "parsed"
    assert by_key[f"form4:{BAD_ACCESSION}"][3]["state"] == "unparsed"
    dumped = json.dumps([p[3] for p in puts])
    assert AGENT not in dumped
    assert "ownershipDocument" not in dumped


class BrokenCache:
    def get(self, provider: str, cache_key: str, valid_for_date: date) -> Any:
        raise SQLAlchemyError("db password=hunter2 select * from secret")

    def put(self, *args: Any, **kwargs: Any) -> Any:
        raise SQLAlchemyError("db password=hunter2 insert into secret")


@respx.mock
def test_cache_failure_is_a_miss_and_logs_a_fixed_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    Mocks()

    with caplog.at_level(logging.DEBUG):
        snapshot = fetch(make_provider(BrokenCache()))

    assert snapshot.quality is ComponentQuality.FRESH
    assert len(snapshot.items) > 0
    assert "provider_cache_unavailable" in caplog.text
    assert "hunter2" not in caplog.text
    assert AGENT not in caplog.text


@respx.mock
@pytest.mark.parametrize(
    ("status", "kind"),
    [(403, "auth"), (429, "rate_limited"), (500, "unavailable")],
)
def test_http_failures_map_to_fixed_messages(status: int, kind: str) -> None:
    route = respx.get(TICKERS_URL).mock(return_value=httpx.Response(status))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "FILINGS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES[kind]
    assert exc.value.__cause__ is None
    assert len(route.calls) == (2 if status in (429, 500) else 1)


@respx.mock
def test_submissions_failure_raises() -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, json=TICKERS))
    respx.get(SUBMISSIONS_URL).mock(return_value=httpx.Response(403))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["auth"]


@respx.mock
def test_malformed_json_raises() -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, text="not json"))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "FILINGS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
@pytest.mark.parametrize("body", [[], "text", 5, None])
def test_unexpected_ticker_shape_raises(body: Any) -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, json=body))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
def test_unexpected_submissions_shape_raises() -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, json=TICKERS))
    respx.get(SUBMISSIONS_URL).mock(return_value=httpx.Response(200, json=[1]))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
def test_user_agent_header_is_sent_on_every_request() -> None:
    mocks = Mocks()

    fetch(make_provider())

    calls = [*mocks.tickers.calls, *mocks.submissions.calls, *mocks.form4.calls]
    assert len(calls) == 12
    assert all(c.request.headers["User-Agent"] == AGENT for c in calls)


@respx.mock
def test_one_shared_deadline_bounds_the_whole_call() -> None:
    mocks = Mocks()
    clock = {"now": 0.0}

    def submissions(request: httpx.Request) -> httpx.Response:
        clock["now"] = 100.0  # the shared six seconds are spent by now
        return httpx.Response(200, json=SUBMISSIONS)

    mocks.submissions.mock(side_effect=submissions)
    provider = make_provider()
    provider._http._clock = lambda: clock["now"]  # type: ignore[attr-defined]

    snapshot = fetch(provider)

    states = [i.details.parse_state for i in insiders_of(snapshot)]
    assert states.count("unparsed") == 10
    assert states.count("not_fetched") == 2
    assert len(mocks.form4.calls) == 0


def _chain_text(error: BaseException | None) -> str:
    parts = []
    while error is not None:
        parts.append(repr(error))
        parts.append(str(error))
        error = error.__cause__ or error.__context__
    return " ".join(parts)


@respx.mock
@pytest.mark.parametrize("status", [403, 429, 500])
def test_user_agent_never_leaks(status: int, caplog: pytest.LogCaptureFixture) -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(status, text=AGENT))
    provider = make_provider()

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(VantageError) as exc:
            fetch(provider)

    for text in (_chain_text(exc.value), repr(provider), caplog.text):
        assert AGENT not in text


@respx.mock
def test_connect_error_does_not_leak_into_the_chain() -> None:
    respx.get(TICKERS_URL).mock(
        side_effect=httpx.ConnectError(f"boom {TICKERS_URL} {AGENT}")
    )

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["unavailable"]
    assert AGENT not in _chain_text(exc.value)
    assert TICKERS_URL not in _chain_text(exc.value)


@respx.mock
def test_documents_and_urls_are_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    Mocks()

    with caplog.at_level(logging.DEBUG):
        fetch(make_provider())

    assert "Example Officer" not in caplog.text
    assert "Apple Inc." not in caplog.text
    assert "sec.gov" not in caplog.text
    assert AGENT not in caplog.text


def test_repr_never_shows_the_user_agent() -> None:
    assert repr(make_provider()) == "EdgarProvider()"


def test_registry_builds_provider_with_user_agent() -> None:
    settings = Settings(_env_file=None, SEC_USER_AGENT=AGENT)

    provider = default_registry().build("filings", "edgar", settings)

    assert isinstance(provider, EdgarProvider)
    assert provider.name == "edgar"


def test_registry_returns_none_without_user_agent() -> None:
    settings = Settings(_env_file=None, SEC_USER_AGENT="")

    assert default_registry().build("filings", "edgar", settings) is None
