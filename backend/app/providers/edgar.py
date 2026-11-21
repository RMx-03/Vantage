"""SEC EDGAR filings and Form 4 insider-transaction provider.

The configured User-Agent travels only in the request header. It is held by the HTTP
client and appears in no attribute, repr, message, cache payload or log line. The cache
holds reduced data only: the ticker map, a few submissions fields and Form 4 parse
fields. It never holds a raw document.
"""

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.domain.research import (
    ComponentQuality,
    EvidenceDetails,
    FilingsSnapshot,
    FundamentalsSnapshot,
    NewsItem,
)
from app.providers.cache import ProviderCache, cache_get_safely, cache_put_safely
from app.providers.http import ProviderHttp, ProviderHttpError, RateLimiter, fail

EDGAR_LIMITER = RateLimiter(8, 1.0)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{name}"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

FILING_FORMS = ("8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A")
INSIDER_FORMS = ("4", "4/A")
INSIDER_LOOKBACK_DAYS = 90
FORM4_FETCH_LIMIT = 10
SUBMISSIONS_KEEP_DAYS = 400

REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)
NET_INCOME_CONCEPT = "NetIncomeLoss"
ANNUAL_FORMS = ("10-K", "10-K/A")
ANNUAL_MIN_DAYS = 350
ANNUAL_MAX_DAYS = 380
_FACT_KEYS = ("start", "end", "val", "form", "fp", "filed")

ERROR_CODE = "FILINGS_PROVIDER_FAILED"
MESSAGES = {
    "auth": "SEC EDGAR refused the request; check SEC_USER_AGENT.",
    "rate_limited": "SEC EDGAR rate limit was reached.",
    "unavailable": "SEC filings could not be retrieved.",
    "rejected": "SEC filings could not be retrieved.",
    "not_found": "SEC filings could not be retrieved.",
    "malformed": "SEC filings could not be retrieved.",
}

_NY = ZoneInfo("America/New_York")
_XSL_PREFIX = re.compile(r"^xslF345X\d\d/")
_ROW_KEYS = (
    "accessionNumber",
    "filingDate",
    "acceptanceDateTime",
    "form",
    "items",
    "primaryDocument",
)
_OWNER_MAX = 120

Row = dict[str, str]


class EdgarProvider:
    name: str = "edgar"

    def __init__(
        self,
        user_agent: str,
        cache: ProviderCache,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        limiter: RateLimiter = EDGAR_LIMITER,
    ) -> None:
        self._cache = cache
        self._http = ProviderHttp(
            timeout_seconds=timeout_seconds,
            limiter=limiter,
            headers={"User-Agent": user_agent},
            transport=transport,
            sleep=sleep,
        )

    def __repr__(self) -> str:
        return "EdgarProvider()"

    # ------------------------------------------------------------------ cache

    def _cache_get(self, key: str, valid_for: date) -> Any | None:
        entry = cache_get_safely(self._cache, self.name, key, valid_for)
        return entry.payload if entry is not None else None

    def _cache_put(
        self,
        key: str,
        valid_for: date,
        payload: Any,
        retrieved_at: datetime,
        *,
        immutable: bool = False,
    ) -> None:
        cache_put_safely(
            self._cache,
            self.name,
            key,
            valid_for,
            payload,
            retrieved_at,
            immutable=immutable,
        )

    # ------------------------------------------------------------------ fetch

    def fetch_filing_evidence(
        self,
        symbol: str,
        cutoff: datetime,
        retrieved_at: datetime,
        lookback_days: int,
    ) -> FilingsSnapshot:
        primary = symbol.strip().upper()
        cutoff_utc = cutoff.astimezone(UTC)
        retrieved_utc = retrieved_at.astimezone(UTC)
        cutoff_date = cutoff_utc.astimezone(_NY).date()
        base: dict[str, Any] = {
            "symbol": primary,
            "provider": self.name,
            "retrieved_at": retrieved_utc,
            "coverage_start": cutoff_utc - timedelta(days=INSIDER_LOOKBACK_DAYS),
            "coverage_end": cutoff_utc,
        }
        missing = FilingsSnapshot(
            **base,
            quality=ComponentQuality.MISSING,
            error_code="NO_SEC_FILER_RECORD",
            items=[],
        )

        try:
            deadline = self._http.deadline()
            # Keyed by retrieval date, as the fundamentals path keys it, so a run
            # downloads the ticker map once however far its cutoff trails.
            tickers = self._ticker_map(
                retrieved_utc.astimezone(_NY).date(), retrieved_utc, deadline
            )
            entry = tickers.get(primary.replace(".", "-"))
            if entry is None:
                found = False
                cik, title = 0, ""
            else:
                found = True
                cik, title = entry
            submissions = None
            if found:
                submissions = self._submissions(
                    cik, cutoff_utc, cutoff_date, retrieved_utc, deadline
                )
        except ProviderHttpError as err:
            raise fail(ERROR_CODE, MESSAGES, err) from None
        if not found or submissions is None:
            return missing

        rows: list[Row] = submissions["filings"]
        filings = self._filing_items(
            rows, cik, cutoff_utc, cutoff_date, retrieved_utc, lookback_days
        )
        insiders = self._insider_items(rows, cik, cutoff_utc, retrieved_utc, deadline)
        all_items = sorted(
            [*filings, *insiders],
            key=lambda i: (i.event_time or cutoff_utc, i.evidence_id),
            reverse=True,
        )
        return FilingsSnapshot(
            **base,
            quality=ComponentQuality.FRESH,
            items=all_items,
            cik=f"{cik:010d}",
            company_name=submissions["name"] or title or None,
            sic_code=submissions["sic"],
            insider_filing_count=len(insiders),
        )

    def _ticker_map(
        self, valid_for: date, retrieved_at: datetime, deadline: float
    ) -> dict[str, tuple[int, str]]:
        cached = self._cache_get("company_tickers", valid_for)
        if isinstance(cached, dict):
            return {
                k: (v[0], v[1])
                for k, v in cached.items()
                if isinstance(v, list) and len(v) == 2
            }
        payload = self._http.get_json(TICKERS_URL, deadline=deadline)
        if not isinstance(payload, dict):
            raise ProviderHttpError("malformed")
        reduced: dict[str, list[Any]] = {}
        for raw in payload.values():
            if not isinstance(raw, dict):
                continue
            cik, ticker, title = raw.get("cik_str"), raw.get("ticker"), raw.get("title")
            if isinstance(cik, bool) or not isinstance(cik, int):
                continue
            if not isinstance(ticker, str) or not ticker.strip():
                continue
            reduced.setdefault(
                ticker.strip().upper(), [cik, title if isinstance(title, str) else ""]
            )
        if not reduced:
            raise ProviderHttpError("malformed")
        self._cache_put("company_tickers", valid_for, reduced, retrieved_at)
        return {k: (v[0], v[1]) for k, v in reduced.items()}

    def _submissions(
        self,
        cik: int,
        cutoff_utc: datetime,
        cutoff_date: date,
        retrieved_at: datetime,
        deadline: float,
    ) -> dict[str, Any] | None:
        key = f"submissions:{cik}"
        cached = self._cache_get(key, cutoff_date)
        if isinstance(cached, dict) and isinstance(cached.get("filings"), list):
            return cached
        try:
            payload = self._http.get_json(
                SUBMISSIONS_URL.format(cik=cik), deadline=deadline
            )
        except ProviderHttpError as err:
            if err.kind == "not_found":
                return None
            raise
        if not isinstance(payload, dict):
            raise ProviderHttpError("malformed")
        reduced = {
            "name": _text(payload.get("name")),
            "sic": _text(payload.get("sic")),
            "filings": _reduce_rows(payload, cutoff_date),
        }
        self._cache_put(key, cutoff_date, reduced, retrieved_at)
        return reduced

    # ------------------------------------------------------------ fundamentals

    def fetch_fundamentals(
        self, symbol: str, retrieved_at: datetime, *, cutoff: datetime | None = None
    ) -> FundamentalsSnapshot:
        primary = symbol.strip().upper()
        retrieved_utc = retrieved_at.astimezone(UTC)
        valid_for = retrieved_utc.astimezone(_NY).date()
        base: dict[str, Any] = {
            "symbol": primary,
            "provider": self.name,
            "retrieved_at": retrieved_utc,
        }
        try:
            deadline = self._http.deadline()
            tickers = self._ticker_map(valid_for, retrieved_utc, deadline)
            entry = tickers.get(primary.replace(".", "-"))
            facts = None
            if entry is not None:
                facts = self._company_facts(
                    entry[0], valid_for, retrieved_utc, deadline
                )
        except ProviderHttpError as err:
            raise fail(ERROR_CODE, MESSAGES, err) from None
        if entry is None:
            return FundamentalsSnapshot(
                **base,
                quality=ComponentQuality.MISSING,
                error_code="NO_SEC_FILER_RECORD",
            )
        filed_by = cutoff.astimezone(_NY).date() if cutoff is not None else None
        selected = _select_fundamentals(facts, filed_by) if facts is not None else None
        if selected is None:
            return FundamentalsSnapshot(
                **base,
                quality=ComponentQuality.MISSING,
                error_code="FUNDAMENTALS_UNAVAILABLE",
            )
        complete = (
            selected["prior_revenue"] is not None and selected["net_income"] is not None
        )
        return FundamentalsSnapshot(
            **base,
            quality=ComponentQuality.FRESH if complete else ComponentQuality.PARTIAL,
            **selected,
        )

    def _company_facts(
        self, cik: int, valid_for: date, retrieved_at: datetime, deadline: float
    ) -> dict[str, list[dict[str, Any]]] | None:
        key = f"companyfacts:{cik}"
        cached = self._cache_get(key, valid_for)
        if isinstance(cached, dict):
            return cached
        try:
            payload = self._http.get_json(
                COMPANYFACTS_URL.format(cik=cik), deadline=deadline
            )
        except ProviderHttpError as err:
            if err.kind == "not_found":
                return None
            raise
        if not isinstance(payload, dict):
            raise ProviderHttpError("malformed")
        reduced = _reduce_facts(payload)
        self._cache_put(key, valid_for, reduced, retrieved_at)
        return reduced

    # ----------------------------------------------------------------- filings

    def _filing_items(
        self,
        rows: list[Row],
        cik: int,
        cutoff_utc: datetime,
        cutoff_date: date,
        retrieved_at: datetime,
        lookback_days: int,
    ) -> list[NewsItem]:
        earliest = cutoff_date - timedelta(days=lookback_days)
        out: list[NewsItem] = []
        for row in rows:
            if row.get("form") not in FILING_FORMS:
                continue
            accepted = _accepted(row)
            filed = _filed(row)
            if accepted is None or filed is None or accepted > cutoff_utc:
                continue
            if not earliest <= filed <= cutoff_date:
                continue
            codes = [c.strip() for c in row.get("items", "").split(",") if c.strip()]
            form = row["form"]
            title = f"Form {form}"
            if codes:
                title += f" (Items {', '.join(codes)})"
            out.append(
                _item(
                    row,
                    cik,
                    title,
                    "filing",
                    accepted,
                    retrieved_at,
                    EvidenceDetails(
                        providers=[self.name], form_type=form, item_codes=codes
                    ),
                )
            )
        return out

    # ---------------------------------------------------------------- insiders

    def _insider_items(
        self,
        rows: list[Row],
        cik: int,
        cutoff_utc: datetime,
        retrieved_at: datetime,
        deadline: float,
    ) -> list[NewsItem]:
        earliest = cutoff_utc - timedelta(days=INSIDER_LOOKBACK_DAYS)
        selected: list[tuple[Row, datetime]] = []
        for row in rows:
            if row.get("form") not in INSIDER_FORMS:
                continue
            accepted = _accepted(row)
            if accepted is None or not earliest < accepted <= cutoff_utc:
                continue
            selected.append((row, accepted))
        selected.sort(key=lambda p: (p[1], p[0]["accessionNumber"]), reverse=True)

        to_fetch = selected[:FORM4_FETCH_LIMIT]
        if to_fetch:
            with ThreadPoolExecutor(max_workers=4) as pool:
                parsed = list(
                    pool.map(
                        lambda p: self._form4(p[0], cik, retrieved_at, deadline),
                        to_fetch,
                    )
                )
        else:
            parsed = []

        out: list[NewsItem] = []
        for index, (row, accepted) in enumerate(selected):
            fields: dict[str, Any] | None = None
            if index < FORM4_FETCH_LIMIT:
                state = "unparsed"
                result = parsed[index]
                if result is not None and result.get("state") == "parsed":
                    state, fields = "parsed", result
            else:
                state = "not_fetched"
            owner = fields.get("owner") if fields else None
            code = fields.get("code") if fields else None
            direction = fields.get("direction") if fields else None
            title = f"Form 4: {owner} ({code})" if owner and code else "Form 4"
            out.append(
                _item(
                    row,
                    cik,
                    title,
                    "insider_transaction",
                    accepted,
                    retrieved_at,
                    EvidenceDetails(
                        providers=[self.name],
                        form_type=row["form"],
                        transaction_code=code,
                        direction=direction,
                        parse_state=state,  # type: ignore[arg-type]
                    ),
                )
            )
        return out

    def _form4(
        self, row: Row, cik: int, retrieved_at: datetime, deadline: float
    ) -> dict[str, Any] | None:
        """Parse fields for one Form 4, or None when the document was not fetched."""
        accession = row["accessionNumber"]
        filed = _filed(row)
        if filed is None:
            return None
        key = f"form4:{accession}"
        cached = self._cache_get(key, filed)
        if isinstance(cached, dict) and cached.get("state") == "parsed":
            return cached
        document = _XSL_PREFIX.sub("", row.get("primaryDocument", ""))
        if not document:
            return None
        url = ARCHIVE_URL.format(
            cik=cik, folder=accession.replace("-", ""), name=document
        )
        try:
            text = self._http.get_text(url, deadline=deadline)
        except ProviderHttpError:
            return None
        result = _parse_form4(text)
        if result.get("state") == "parsed":
            # An unparsed result is never cached: a transient notice page or odd
            # body must not pin the filing as unparsed forever.
            self._cache_put(key, filed, result, retrieved_at, immutable=True)
        return result


# ---------------------------------------------------------------------- helpers


def _text(value: object) -> str | None:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        text = str(value).strip()
        return text or None
    return None


def _accepted(row: Row) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(
            row["acceptanceDateTime"].replace("Z", "+00:00")
        )
    except (KeyError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _filed(row: Row) -> date | None:
    try:
        return date.fromisoformat(row["filingDate"])
    except (KeyError, ValueError):
        return None


def _reduce_rows(payload: dict[str, Any], cutoff_date: date) -> list[Row]:
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        return []
    columns = {k: recent.get(k) for k in _ROW_KEYS}
    if not all(isinstance(v, list) for v in columns.values()):
        return []
    oldest = cutoff_date - timedelta(days=SUBMISSIONS_KEEP_DAYS)
    wanted = {*FILING_FORMS, *INSIDER_FORMS}
    rows: list[Row] = []
    for values in zip(*(columns[k] for k in _ROW_KEYS), strict=False):
        row = {
            k: v if isinstance(v, str) else ""
            for k, v in zip(_ROW_KEYS, values, strict=True)
        }
        filed = _filed(row)
        if row["form"] in wanted and filed is not None and filed >= oldest:
            if row["accessionNumber"]:
                rows.append(row)
    return rows


def _fact_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class _Annual:
    __slots__ = ("end", "filed", "form", "start", "val")

    def __init__(
        self, start: date, end: date, filed: date, form: str, val: float
    ) -> None:
        self.start = start
        self.end = end
        self.filed = filed
        self.form = form
        self.val = val


def _annual(raw: object) -> _Annual | None:
    """One annual 10-K fact, or None when it is not annual or is malformed."""
    if not isinstance(raw, dict):
        return None
    form, val = raw.get("form"), raw.get("val")
    if form not in ANNUAL_FORMS or raw.get("fp") != "FY":
        return None
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    start, end, filed = (_fact_date(raw.get(k)) for k in ("start", "end", "filed"))
    if start is None or end is None or filed is None:
        return None
    if not ANNUAL_MIN_DAYS <= (end - start).days <= ANNUAL_MAX_DAYS:
        return None
    return _Annual(start, end, filed, form, float(val))


def _reduce_facts(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Keep only the annual USD facts of the five concepts, with selection fields."""
    facts = payload.get("facts")
    gaap = facts.get("us-gaap") if isinstance(facts, dict) else None
    if not isinstance(gaap, dict):
        return {}
    reduced: dict[str, list[dict[str, Any]]] = {}
    for concept in (*REVENUE_CONCEPTS, NET_INCOME_CONCEPT):
        node = gaap.get(concept)
        units = node.get("units") if isinstance(node, dict) else None
        rows = units.get("USD") if isinstance(units, dict) else None
        if not isinstance(rows, list):
            continue
        kept = [
            {k: row[k] for k in _FACT_KEYS} for row in rows if _annual(row) is not None
        ]
        if kept:
            reduced[concept] = kept
    return reduced


def _latest_by_end(rows: object, filed_by: date | None = None) -> dict[date, _Annual]:
    """Annual facts keyed by period end, keeping the latest filed of each end.

    Facts filed after `filed_by` are ignored, so a run never sees a later filing.
    """
    out: dict[date, _Annual] = {}
    if not isinstance(rows, list):
        return out
    for raw in rows:
        fact = _annual(raw)
        if fact is None or (filed_by is not None and fact.filed > filed_by):
            continue
        current = out.get(fact.end)
        if current is None or fact.filed > current.filed:
            out[fact.end] = fact
    return out


def _select_fundamentals(
    facts: dict[str, list[dict[str, Any]]], filed_by: date | None = None
) -> dict[str, Any] | None:
    best: tuple[str, dict[date, _Annual], date] | None = None
    for concept in REVENUE_CONCEPTS:
        by_end = _latest_by_end(facts.get(concept), filed_by)
        if not by_end:
            continue
        latest = max(by_end)
        if best is None or latest > best[2]:
            best = (concept, by_end, latest)
    if best is None:
        return None
    concept, by_end, end = best
    current = by_end[end]
    prior_ends = [
        e for e in by_end if ANNUAL_MIN_DAYS <= (end - e).days <= ANNUAL_MAX_DAYS
    ]
    prior = by_end[max(prior_ends)] if prior_ends else None
    income = _latest_by_end(facts.get(NET_INCOME_CONCEPT), filed_by).get(end)
    return {
        "fiscal_year": end.year,
        "period_end": end,
        "form": current.form,
        "revenue": current.val,
        "prior_revenue": prior.val if prior is not None else None,
        "net_income": income.val if income is not None else None,
        "revenue_concept": concept,
    }


def _item(
    row: Row,
    cik: int,
    title: str,
    source_type: Any,
    accepted: datetime,
    retrieved_at: datetime,
    details: EvidenceDetails,
) -> NewsItem:
    accession = row["accessionNumber"]
    return NewsItem(
        evidence_id=f"sec-{accession}",
        provider="edgar",
        publisher="SEC EDGAR",
        title=title,
        url=ARCHIVE_URL.format(
            cik=cik,
            folder=accession.replace("-", ""),
            name=f"{accession}-index.htm",
        ),
        event_time=accepted,
        retrieved_at=retrieved_at,
        source_type=source_type,
        details=details,
    )


def _parse_form4(text: str) -> dict[str, Any]:
    """Reduce a Form 4 document to owner, transaction code and direction."""
    try:
        root = ElementTree.fromstring(text)
    except (ElementTree.ParseError, DefusedXmlException, ValueError):
        return {"state": "unparsed"}
    transaction = root.find("nonDerivativeTable/nonDerivativeTransaction")
    if transaction is None:
        transaction = root.find("derivativeTable/derivativeTransaction")
    if transaction is None:
        return {"state": "unparsed"}
    code = _find_text(transaction, "transactionCoding/transactionCode")
    flag = _find_text(
        transaction, "transactionAmounts/transactionAcquiredDisposedCode/value"
    )
    owner = _find_text(root, "reportingOwner/reportingOwnerId/rptOwnerName")
    if owner is not None:
        owner = " ".join(owner.split())[:_OWNER_MAX] or None
    direction = {"A": "acquired", "D": "disposed"}.get(flag or "")
    if code is None and owner is None:
        return {"state": "unparsed"}
    return {"state": "parsed", "owner": owner, "code": code, "direction": direction}


def _find_text(node: Any, path: str) -> str | None:
    found = node.find(path)
    if found is None or found.text is None:
        return None
    text = found.text.strip()
    return text or None
