import copy
import json
import logging
from datetime import UTC, date, datetime
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
from app.providers.edgar import (
    NET_INCOME_CONCEPT,
    REVENUE_CONCEPTS,
    EdgarProvider,
)
from app.providers.http import RateLimiter
from app.providers.registry import build_providers

AGENT = "Vantage Test Suite sec-contact-7731@example.invalid"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
FACTS_20F_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001046179.json"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "providers" / "edgar"
RETRIEVED = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
TICKERS = json.loads((FIXTURES / "company_tickers.json").read_text())
FACTS = json.loads((FIXTURES / "companyfacts_aapl.json").read_text())
FACTS_20F = json.loads((FIXTURES / "companyfacts_20f.json").read_text())
RCC = "RevenueFromContractWithCustomerExcludingAssessedTax"

MESSAGES = {
    "auth": "SEC EDGAR refused the request; check SEC_USER_AGENT.",
    "rate_limited": "SEC EDGAR rate limit was reached.",
    "unavailable": "SEC filings could not be retrieved.",
    "malformed": "SEC filings could not be retrieved.",
}


def make_provider(cache: Any = None) -> EdgarProvider:
    return EdgarProvider(
        AGENT,
        cache if cache is not None else InMemoryProviderCache(),
        timeout_seconds=6.0,
        sleep=lambda seconds: None,
        limiter=RateLimiter(10_000, 1.0),
    )


def fetch(provider: EdgarProvider, symbol: str = "aapl") -> Any:
    return provider.fetch_fundamentals(symbol, RETRIEVED)


def fact(
    start: str, end: str, val: Any, *, form: str = "10-K", fp: str = "FY", filed: str
) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "val": val,
        "form": form,
        "fp": fp,
        "filed": filed,
    }


def doc(**concepts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "facts": {
            "us-gaap": {
                name: {"units": {"USD": rows}} for name, rows in concepts.items()
            }
        }
    }


def mock_tickers() -> respx.Route:
    return respx.get(TICKERS_URL).mock(return_value=httpx.Response(200, json=TICKERS))


def mock_facts(body: Any = None, url: str = FACTS_URL) -> respx.Route:
    return respx.get(url).mock(
        return_value=httpx.Response(200, json=FACTS if body is None else body)
    )


def test_concepts_are_recorded_in_code() -> None:
    assert REVENUE_CONCEPTS == (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    )
    assert NET_INCOME_CONCEPT == "NetIncomeLoss"


@respx.mock
def test_latest_filed_value_wins_with_prior_and_net_income() -> None:
    mock_tickers()
    mock_facts()

    snapshot = fetch(make_provider())

    assert snapshot.provider == "edgar"
    assert snapshot.symbol == "AAPL"
    assert snapshot.quality is ComponentQuality.FRESH
    assert snapshot.error_code is None
    assert snapshot.retrieved_at == RETRIEVED
    assert snapshot.revenue == 416200000000.0  # the later 10-K/A of the same year
    assert snapshot.prior_revenue == 391035000000.0
    assert snapshot.net_income == 112010000000.0
    assert snapshot.period_end == date(2025, 9, 27)
    assert snapshot.fiscal_year == 2025
    assert snapshot.form == "10-K/A"
    assert snapshot.revenue_concept == RCC


@respx.mock
def test_quarterly_and_older_concepts_are_ignored() -> None:
    mock_tickers()
    mock_facts()

    snapshot = fetch(make_provider())

    assert snapshot.period_end != date(2026, 6, 27)
    assert snapshot.revenue_concept != "SalesRevenueNet"
    assert snapshot.net_income == 112010000000.0  # not the 10-Q figure


@respx.mock
def test_tie_on_period_end_goes_to_concept_order() -> None:
    mock_tickers()
    row = fact("2024-09-29", "2025-09-27", 100.0, filed="2025-10-31")
    prior = fact("2023-10-01", "2024-09-28", 90.0, filed="2024-11-01")
    other = fact("2024-09-29", "2025-09-27", 555.0, filed="2025-10-31")
    mock_facts(doc(SalesRevenueNet=[other], Revenues=[prior, row], **{RCC: [other]}))

    snapshot = fetch(make_provider())

    assert snapshot.revenue_concept == "Revenues"
    assert snapshot.revenue == 100.0
    assert snapshot.prior_revenue == 90.0


@respx.mock
def test_missing_prior_year_is_partial() -> None:
    mock_tickers()
    body = copy.deepcopy(FACTS)
    rows = body["facts"]["us-gaap"][RCC]["units"]["USD"]
    body["facts"]["us-gaap"][RCC]["units"]["USD"] = [
        r for r in rows if r["end"] != "2024-09-28"
    ]
    mock_facts(body)

    snapshot = fetch(make_provider())

    assert snapshot.quality is ComponentQuality.PARTIAL
    assert snapshot.error_code is None
    assert snapshot.prior_revenue is None
    assert snapshot.revenue == 416200000000.0


@respx.mock
def test_missing_net_income_is_partial() -> None:
    mock_tickers()
    body = copy.deepcopy(FACTS)
    del body["facts"]["us-gaap"]["NetIncomeLoss"]
    mock_facts(body)

    snapshot = fetch(make_provider())

    assert snapshot.quality is ComponentQuality.PARTIAL
    assert snapshot.net_income is None
    assert snapshot.prior_revenue == 391035000000.0


@respx.mock
@pytest.mark.parametrize(
    ("end", "selected"),
    [
        ("2025-09-12", False),  # 348 days
        ("2025-09-14", True),  # 350 days, inclusive
        ("2025-10-14", True),  # 380 days, inclusive
        ("2025-10-15", False),  # 381 days
    ],
)
def test_duration_bounds_are_inclusive(end: str, selected: bool) -> None:
    mock_tickers()
    mock_facts(doc(Revenues=[fact("2024-09-29", end, 7.0, filed="2025-11-01")]))

    snapshot = fetch(make_provider())

    if selected:
        assert snapshot.revenue == 7.0
        assert snapshot.period_end == date.fromisoformat(end)
    else:
        assert snapshot.quality is ComponentQuality.MISSING
        assert snapshot.error_code == "FUNDAMENTALS_UNAVAILABLE"


@respx.mock
def test_prior_year_bounds_are_inclusive() -> None:
    mock_tickers()
    current = fact("2024-09-29", "2025-09-27", 10.0, filed="2025-10-31")
    older = fact("2023-09-13", "2024-09-12", 8.0, filed="2024-10-31")  # 380 days
    mock_facts(doc(Revenues=[current, older]))

    snapshot = fetch(make_provider())

    assert snapshot.prior_revenue == 8.0


@respx.mock
def test_malformed_facts_are_skipped_without_raising() -> None:
    mock_tickers()
    good = fact("2024-09-29", "2025-09-27", 10.0, filed="2025-10-31")
    bad = [
        fact("2024-09-29", "2026-09-27", 1.0, filed="2025-10-31"),
        fact("not-a-date", "2025-09-27", 2.0, filed="2025-10-31"),
        fact("2024-09-29", "2025-09-27", None, filed="2025-10-31"),
        fact("2024-09-29", "2025-09-27", "12", filed="2025-10-31"),
        fact("2024-09-29", "2025-09-27", 3.0, filed="bad"),
        fact("2024-09-29", "2025-09-27", True, filed="2025-11-30"),
        {"end": "2025-09-27", "val": 4.0, "form": "10-K", "fp": "FY"},
        fact("2024-09-29", "2025-09-27", 5.0, form="10-Q", filed="2025-12-01"),
        fact("2024-09-29", "2025-09-27", 6.0, fp="Q4", filed="2025-12-01"),
    ]
    mock_facts(doc(Revenues=[*bad, good]))

    snapshot = fetch(make_provider())

    assert snapshot.revenue == 10.0


@respx.mock
def test_twenty_f_filer_has_no_annual_revenue() -> None:
    respx.get(TICKERS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"0": {"cik_str": 1046179, "ticker": "TSM", "title": "TSMC"}},
        )
    )
    mock_facts(FACTS_20F, FACTS_20F_URL)

    snapshot = fetch(make_provider(), "tsm")

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "FUNDAMENTALS_UNAVAILABLE"
    assert snapshot.revenue is None
    assert snapshot.revenue_concept is None


@respx.mock
def test_ticker_miss_is_missing_without_a_facts_request() -> None:
    mock_tickers()
    facts = mock_facts()

    snapshot = fetch(make_provider(), "zzzz")

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "NO_SEC_FILER_RECORD"
    assert snapshot.symbol == "ZZZZ"
    assert facts.call_count == 0


@respx.mock
def test_facts_not_found_is_unavailable_not_a_failure() -> None:
    mock_tickers()
    respx.get(FACTS_URL).mock(return_value=httpx.Response(404))

    snapshot = fetch(make_provider())

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "FUNDAMENTALS_UNAVAILABLE"


@respx.mock
def test_second_call_uses_the_cache_and_payload_is_reduced() -> None:
    tickers = mock_tickers()
    facts = mock_facts()
    cache = InMemoryProviderCache()
    provider = make_provider(cache)

    first = fetch(provider)
    second = fetch(provider)

    assert tickers.call_count == 1
    assert facts.call_count == 1
    assert first.model_dump() == second.model_dump()
    entry = cache.get("edgar", "companyfacts:320193", date(2026, 11, 13))
    assert entry is not None
    payload = entry.payload
    assert set(payload) == {RCC, "SalesRevenueNet", NET_INCOME_CONCEPT}
    for rows in payload.values():
        for row in rows:
            assert set(row) == {"start", "end", "val", "form", "fp", "filed"}
            assert row["fp"] == "FY"
            assert row["form"] in ("10-K", "10-K/A")
    text = json.dumps(payload)
    assert "Assets" not in text
    assert "EntityCommonStockSharesOutstanding" not in text
    assert "2026-06-27" not in text  # the quarterly fact is not cached


@respx.mock
def test_ticker_map_is_downloaded_once_across_filings_and_fundamentals() -> None:
    # The run's cutoff is the previous session; its retrieval is the next day.
    cutoff = datetime(2026, 11, 13, 21, 0, tzinfo=UTC)
    retrieved = datetime(2026, 11, 14, 22, 0, tzinfo=UTC)
    tickers = mock_tickers()
    provider = make_provider()

    provider.fetch_filing_evidence("zzzz", cutoff, retrieved, 30)
    provider.fetch_fundamentals("zzzz", retrieved)

    assert tickers.call_count == 1


@respx.mock
def test_cache_failure_is_a_miss(caplog: pytest.LogCaptureFixture) -> None:
    mock_tickers()
    mock_facts()

    class Broken(InMemoryProviderCache):
        def get(self, *args: Any, **kwargs: Any) -> Any:
            raise SQLAlchemyError("db password=hunter2")

        def put(self, *args: Any, **kwargs: Any) -> Any:
            raise SQLAlchemyError("db password=hunter2")

    with caplog.at_level(logging.DEBUG):
        snapshot = fetch(make_provider(Broken()))

    assert snapshot.quality is ComponentQuality.FRESH
    assert "provider_cache_unavailable" in caplog.text
    assert "hunter2" not in caplog.text


@respx.mock
@pytest.mark.parametrize(
    ("status", "kind"),
    [(403, "auth"), (429, "rate_limited"), (500, "unavailable")],
)
def test_facts_http_failures_map_to_fixed_messages(status: int, kind: str) -> None:
    mock_tickers()
    respx.get(FACTS_URL).mock(return_value=httpx.Response(status))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "FILINGS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES[kind]
    assert exc.value.__cause__ is None


@respx.mock
def test_ticker_map_failure_raises() -> None:
    respx.get(TICKERS_URL).mock(return_value=httpx.Response(403))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.code == "FILINGS_PROVIDER_FAILED"
    assert exc.value.safe_message == MESSAGES["auth"]


@respx.mock
@pytest.mark.parametrize("body", [[], "text"])
def test_non_object_facts_document_raises(body: Any) -> None:
    mock_tickers()
    respx.get(FACTS_URL).mock(return_value=httpx.Response(200, json=body))

    with pytest.raises(VantageError) as exc:
        fetch(make_provider())

    assert exc.value.safe_message == MESSAGES["malformed"]


@respx.mock
@pytest.mark.parametrize("body", [{}, {"facts": []}, {"facts": {"us-gaap": 3}}])
def test_facts_without_usable_us_gaap_are_unavailable(body: Any) -> None:
    mock_tickers()
    respx.get(FACTS_URL).mock(return_value=httpx.Response(200, json=body))

    snapshot = fetch(make_provider())

    assert snapshot.quality is ComponentQuality.MISSING
    assert snapshot.error_code == "FUNDAMENTALS_UNAVAILABLE"


@respx.mock
def test_user_agent_never_leaks_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    mock_tickers()
    respx.get(FACTS_URL).mock(return_value=httpx.Response(500))

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(VantageError) as exc:
            fetch(make_provider())

    assert AGENT not in exc.value.safe_message
    assert AGENT not in caplog.text
    assert exc.value.__context__ is None or AGENT not in str(exc.value.__context__)


@respx.mock
def test_one_deadline_is_shared_by_both_requests() -> None:
    mock_tickers()
    mock_facts()
    provider = make_provider()
    calls: list[int] = []
    original = provider._http.deadline

    def counting() -> float:
        calls.append(1)
        return original()

    provider._http.deadline = counting  # type: ignore[method-assign]

    fetch(provider)

    assert len(calls) == 1


def test_registry_derives_the_fundamentals_role_from_edgar() -> None:
    settings = Settings(_env_file=None, FILINGS_PROVIDER="edgar", SEC_USER_AGENT=AGENT)

    providers = build_providers(settings)

    assert isinstance(providers.fundamentals, EdgarProvider)
    assert providers.fundamentals is providers.filings
