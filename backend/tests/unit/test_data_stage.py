import logging
import threading
import time
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.domain.errors import VantageError
from app.domain.research import (
    ComponentQuality,
    FilingsSnapshot,
    FundamentalsSnapshot,
    MacroSnapshot,
    MarketSnapshot,
    NewsSnapshot,
    PriceCrossCheckSnapshot,
    RoleQuality,
)
from app.providers.llm import DisabledInterpretationProvider
from app.providers.registry import ProviderSet
from app.services import data_stage
from app.services.data_stage import collect_inputs

NOW = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 11, 13, 21, 0, tzinfo=UTC)
SESSIONS = [date(2026, 11, 11), date(2026, 11, 12), date(2026, 11, 13)]
SECRET = "super-secret-token-value"


class StubMarket:
    name = "mkt"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple] = []
        self.context_symbols: tuple[str, ...] = ()

    def fetch_daily_snapshot(
        self, symbol, start_session, end_session, retrieved_at, *, context_symbols=()
    ):
        self.calls.append((symbol, start_session, end_session, retrieved_at))
        self.context_symbols = context_symbols
        if self.error is not None:
            raise self.error
        return MarketSnapshot(
            symbol=symbol,
            bars=[],
            provider=self.name,
            retrieved_at=retrieved_at,
            as_of=retrieved_at,
            latest_completed_session=end_session,
            content_hash="a" * 64,
        )


class StubNews:
    def __init__(self, name: str, error: Exception | None = None) -> None:
        self.name = name
        self.error = error
        self.args: tuple = ()
        self.snapshot: NewsSnapshot | None = None

    def fetch_company_news(self, symbol, cutoff, retrieved_at, lookback_days, limit):
        self.args = (symbol, cutoff, retrieved_at, lookback_days, limit)
        if self.error is not None:
            raise self.error
        self.snapshot = NewsSnapshot(
            symbol=symbol,
            items=[],
            provider=self.name,
            retrieved_at=retrieved_at,
            quality=ComponentQuality.FRESH,
        )
        return self.snapshot


def _filings(
    sic: str | None,
    quality: ComponentQuality = ComponentQuality.FRESH,
    error_code: str | None = None,
) -> FilingsSnapshot:
    return FilingsSnapshot(
        symbol="AAPL",
        items=[],
        provider="edgar",
        retrieved_at=NOW,
        quality=quality,
        error_code=error_code,
        sic_code=sic,
    )


class StubFilings:
    name = "edgar"

    def __init__(self, snapshot: FilingsSnapshot | None = None, error=None) -> None:
        self.snapshot = snapshot
        self.error = error
        self.args: tuple = ()

    def fetch_filing_evidence(self, symbol, cutoff, retrieved_at, lookback_days):
        self.args = (symbol, cutoff, retrieved_at, lookback_days)
        if self.error is not None:
            raise self.error
        return self.snapshot or _filings("3571")


class StubFundamentals:
    name = "edgar-facts"

    def __init__(self) -> None:
        self.calls = 0
        self.args: tuple = ()

    def fetch_fundamentals(self, symbol, retrieved_at, *, cutoff=None):
        self.calls += 1
        self.args = (symbol, retrieved_at)
        self.cutoff = cutoff
        return FundamentalsSnapshot(
            symbol=symbol,
            provider=self.name,
            retrieved_at=retrieved_at,
            quality=ComponentQuality.FRESH,
        )


class StubMacro:
    name = "fred"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.args: tuple = ()

    def fetch_macro(self, end_session, retrieved_at):
        self.args = (end_session, retrieved_at)
        if self.error is not None:
            raise self.error
        return MacroSnapshot(
            provider=self.name,
            retrieved_at=retrieved_at,
            quality=ComponentQuality.FRESH,
        )


class StubCrossCheck:
    name = "tiingo"

    def __init__(self, gate: threading.Event | None = None) -> None:
        self.gate = gate
        self.args: tuple = ()

    def fetch_adjusted_closes(self, symbol, start_session, end_session, retrieved_at):
        self.args = (symbol, start_session, end_session, retrieved_at)
        if self.gate is not None:
            self.gate.wait(timeout=30)
        return PriceCrossCheckSnapshot(
            symbol=symbol,
            provider=self.name,
            retrieved_at=retrieved_at,
            quality=ComponentQuality.FRESH,
        )


def _set(**overrides) -> ProviderSet:
    base = ProviderSet(
        market=StubMarket(),
        news=(StubNews("alpaca"),),
        filings=StubFilings(),
        fundamentals=StubFundamentals(),
        macro=StubMacro(),
        crosscheck=StubCrossCheck(),
        llm=DisabledInterpretationProvider(),
        not_configured=(),
    )
    return replace(base, **overrides)


def _collect(providers: ProviderSet, **kwargs):
    params = dict(
        symbol="AAPL",
        now=NOW,
        cutoff=CUTOFF,
        sessions=SESSIONS,
        news_lookback_days=7,
        role_timeout_seconds=2.0,
        run_id="run-1",
    )
    params.update(kwargs)
    return collect_inputs(providers, **params)


def test_happy_path_passes_context_symbols_and_builds_six_records() -> None:
    providers = _set()
    out = _collect(providers)

    assert providers.market.context_symbols == ("SPY", "XLK")
    assert providers.market.calls[0][1:] == (SESSIONS[0], SESSIONS[-1], NOW)
    assert out.market.as_of == CUTOFF
    assert out.market.latest_completed_session == SESSIONS[-1]
    assert out.inputs.sector_etf == "XLK"
    assert out.inputs.failed == {}
    assert out.inputs.not_configured == frozenset()
    assert out.inputs.filings is not None
    assert out.inputs.fundamentals is not None
    assert out.inputs.macro is not None
    assert out.inputs.crosscheck is not None
    assert [r.role for r in out.records] == [
        "market",
        "news",
        "filings",
        "fundamentals",
        "macro",
        "crosscheck",
    ]
    assert all(r.quality == RoleQuality.FRESH for r in out.records)
    assert [r.provider for r in out.records] == [
        "mkt",
        "alpaca",
        "edgar",
        "edgar-facts",
        "fred",
        "tiingo",
    ]
    assert out.records[0].content_hash == "a" * 64
    assert all(r.content_hash is None for r in out.records[1:])
    assert providers.filings.args == ("AAPL", CUTOFF, NOW, 30)
    assert providers.news[0].args == ("AAPL", CUTOFF, NOW, 7, 10)
    assert providers.fundamentals.args == ("AAPL", NOW)
    assert providers.fundamentals.cutoff == CUTOFF
    assert providers.macro.args == (SESSIONS[-1], NOW)
    assert providers.crosscheck.args == ("AAPL", SESSIONS[0], SESSIONS[-1], NOW)
    # one provider and success: the merged snapshot is the provider's own object
    assert out.news is providers.news[0].snapshot


def test_filings_not_configured() -> None:
    providers = _set(
        filings=None,
        fundamentals=None,
        not_configured=("filings", "fundamentals"),
    )
    out = _collect(providers)

    assert providers.market.context_symbols == ("SPY",)
    assert out.inputs.not_configured == frozenset({"filings", "fundamentals"})
    assert out.inputs.filings is None
    assert out.inputs.fundamentals is None
    assert out.inputs.sector_etf is None
    assert out.inputs.failed == {}
    by_role = {r.role: r for r in out.records}
    for role in ("filings", "fundamentals"):
        assert by_role[role].provider is None
        assert by_role[role].retrieved_at is None
        assert by_role[role].quality == RoleQuality.NOT_CONFIGURED


def test_filings_failure_fails_fundamentals_without_calling_it() -> None:
    providers = _set(
        filings=StubFilings(
            error=VantageError(code="FILINGS_PROVIDER_FAILED", safe_message="x")
        )
    )
    out = _collect(providers)

    assert out.inputs.failed["filings"] == "FILINGS_PROVIDER_FAILED"
    assert out.inputs.failed["fundamentals"] == "FILINGS_PROVIDER_FAILED"
    assert out.inputs.filings is None
    assert out.inputs.fundamentals is None
    assert out.inputs.not_configured == frozenset()
    assert providers.fundamentals.calls == 0
    assert providers.market.context_symbols == ("SPY",)
    by_role = {r.role: r for r in out.records}
    assert by_role["filings"].quality == RoleQuality.FAILED
    assert by_role["filings"].error_code == "FILINGS_PROVIDER_FAILED"
    assert by_role["fundamentals"].quality == RoleQuality.FAILED
    assert by_role["macro"].quality == RoleQuality.FRESH


def test_filings_snapshot_returned_failed_is_kept_not_listed_failed() -> None:
    providers = _set(
        filings=StubFilings(
            _filings("3571", ComponentQuality.FAILED, "FILINGS_PROVIDER_FAILED")
        )
    )
    out = _collect(providers)

    assert out.inputs.filings is not None
    assert "filings" not in out.inputs.failed
    assert out.inputs.sector_etf is None
    assert providers.market.context_symbols == ("SPY",)
    assert providers.fundamentals.calls == 0
    assert out.inputs.failed["fundamentals"] == "FILINGS_PROVIDER_FAILED"


def test_no_filer_record_makes_fundamentals_missing_without_calling_it() -> None:
    providers = _set(
        filings=StubFilings(
            _filings(None, ComponentQuality.MISSING, "NO_SEC_FILER_RECORD")
        )
    )
    out = _collect(providers)

    assert providers.fundamentals.calls == 0
    assert out.inputs.fundamentals is not None
    assert out.inputs.fundamentals.quality == ComponentQuality.MISSING
    assert out.inputs.fundamentals.error_code == "NO_SEC_FILER_RECORD"
    assert "fundamentals" not in out.inputs.failed
    rec = {r.role: r for r in out.records}["fundamentals"]
    assert rec.quality == RoleQuality.MISSING
    assert rec.error_code == "NO_SEC_FILER_RECORD"


def test_macro_runtime_error_is_failed_and_logs_type_name_only(caplog) -> None:
    providers = _set(macro=StubMacro(error=RuntimeError(SECRET)))
    with caplog.at_level(logging.DEBUG):
        out = _collect(providers)

    assert out.inputs.failed["macro"] == "MACRO_PROVIDER_FAILED"
    assert out.inputs.macro is None
    assert "macro" not in out.inputs.not_configured
    assert SECRET not in caplog.text
    lines = [r.getMessage() for r in caplog.records]
    assert "provider_role_failed role=macro error=RuntimeError" in lines
    rec = {r.role: r for r in out.records}["macro"]
    assert rec.quality == RoleQuality.FAILED
    assert rec.error_code == "MACRO_PROVIDER_FAILED"
    assert rec.retrieved_at == NOW


def test_blocked_crosscheck_times_out_without_hanging(monkeypatch, caplog) -> None:
    monkeypatch.setattr(data_stage, "ROLE_WAIT_MARGIN_SECONDS", 0.1)
    gate = threading.Event()
    providers = _set(crosscheck=StubCrossCheck(gate))
    try:
        started = time.monotonic()
        with caplog.at_level(logging.DEBUG):
            out = _collect(providers, role_timeout_seconds=0.2)
        elapsed = time.monotonic() - started
    finally:
        gate.set()

    assert elapsed < 2.0
    assert out.inputs.failed["crosscheck"] == "PRICE_CROSSCHECK_FAILED"
    assert out.inputs.crosscheck is None
    assert out.inputs.macro is not None
    assert "provider_role_failed role=crosscheck error=Timeout" in [
        r.getMessage() for r in caplog.records
    ]


def test_failing_news_provider_gives_failed_snapshot_and_partial_merge() -> None:
    good = StubNews("alpaca")
    bad = StubNews("finnhub", error=RuntimeError(SECRET))
    out = _collect(_set(news=(good, bad)))

    assert out.news.quality == ComponentQuality.PARTIAL
    assert out.records[1].quality == RoleQuality.PARTIAL
    assert out.records[1].provider == out.news.provider
    assert SECRET not in repr(out.news)


def test_single_failing_news_provider_error_code() -> None:
    plain = _collect(_set(news=(StubNews("finnhub", error=RuntimeError("x")),)))
    assert plain.news.quality == ComponentQuality.FAILED
    assert plain.news.error_code == "NEWS_PROVIDER_FAILED"
    assert plain.news.provider == "finnhub"

    coded = _collect(
        _set(
            news=(
                StubNews(
                    "finnhub",
                    error=VantageError(code="NEWS_RATE_LIMITED", safe_message="x"),
                ),
            )
        )
    )
    assert coded.news.error_code == "NEWS_RATE_LIMITED"


def test_no_news_provider_gives_none_snapshot() -> None:
    out = _collect(_set(news=()))

    assert out.news.provider == "none"
    assert out.news.quality == ComponentQuality.FAILED
    assert out.news.error_code == "NEWS_PROVIDER_FAILED"
    assert out.records[1].provider is None
    assert out.records[1].quality == RoleQuality.NOT_CONFIGURED
    assert out.records[1].retrieved_at is None
    assert out.records[1].error_code is None


def test_market_vantage_error_propagates() -> None:
    providers = _set(
        market=StubMarket(
            VantageError(code="MARKET_DATA_PROVIDER_FAILED", safe_message="down")
        )
    )
    with pytest.raises(VantageError) as exc:
        _collect(providers)
    assert exc.value.code == "MARKET_DATA_PROVIDER_FAILED"


def test_market_non_vantage_error_propagates_unchanged() -> None:
    with pytest.raises(RuntimeError):
        _collect(_set(market=StubMarket(RuntimeError("boom"))))


def test_invalid_price_series_gives_failed_market_snapshot() -> None:
    err = VantageError(
        code="INVALID_PRICE_SERIES",
        safe_message="bad",
        missing_value_count=2,
        duplicate_session_count=1,
    )
    out = _collect(_set(market=StubMarket(err)))

    assert out.market.quality == ComponentQuality.FAILED
    assert out.market.error_code == "INVALID_PRICE_SERIES"
    assert out.market.missing_value_count == 2
    assert out.market.duplicate_session_count == 1
    assert out.market.bars == []
    assert out.market.as_of == CUTOFF
    assert out.market.latest_completed_session == SESSIONS[-1]
    assert out.records[0].quality == RoleQuality.FAILED
    assert out.records[0].content_hash == out.market.content_hash


def test_no_market_provider_raises_not_configured_message() -> None:
    with pytest.raises(VantageError) as exc:
        _collect(_set(market=None))
    assert exc.value.code == "MARKET_DATA_PROVIDER_FAILED"
    assert exc.value.safe_message == "Market data provider is not configured."


def test_slow_market_raises_when_cap_passes(monkeypatch) -> None:
    monkeypatch.setattr(data_stage, "ROLE_WAIT_MARGIN_SECONDS", 0.1)
    gate = threading.Event()

    class SlowMarket(StubMarket):
        def fetch_daily_snapshot(self, *args, **kwargs):
            gate.wait(timeout=30)
            return super().fetch_daily_snapshot(*args, **kwargs)

    try:
        with pytest.raises(VantageError) as exc:
            _collect(_set(market=SlowMarket()), role_timeout_seconds=0.2)
    finally:
        gate.set()
    assert exc.value.code == "MARKET_DATA_PROVIDER_FAILED"
    assert exc.value.safe_message == "Market prices could not be retrieved."


def test_provider_request_spans_carry_role_and_provider_name(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(data_stage, "get_tracer", lambda: tracer)

    with tracer.start_as_current_span("run_root") as root:
        _collect(_set())

    spans = exporter.get_finished_spans()
    requests = [s for s in spans if s.name == "provider_request"]
    pairs = {
        (s.attributes["vantage.provider.role"], s.attributes["vantage.provider.name"])
        for s in requests
    }
    assert pairs == {
        ("market", "mkt"),
        ("news", "alpaca"),
        ("filings", "edgar"),
        ("fundamentals", "edgar-facts"),
        ("macro", "fred"),
        ("crosscheck", "tiingo"),
    }
    assert all(s.attributes["vantage.run_id"] == "run-1" for s in requests)
    role_spans = [s for s in spans if s.name.startswith("fetch_")]
    assert {s.name for s in role_spans} == {
        "fetch_market_snapshot",
        "fetch_news_snapshot",
        "fetch_filings_snapshot",
        "fetch_fundamentals_snapshot",
        "fetch_macro_snapshot",
        "fetch_crosscheck_snapshot",
    }
    # worker spans are children of the calling thread's span (context propagated)
    trace_id = root.get_span_context().trace_id
    assert all(s.context.trace_id == trace_id for s in role_spans)
    assert all(s.parent is not None for s in role_spans)


class HangingNews:
    name = "slowwire"

    def __init__(self, gate: threading.Event) -> None:
        self.gate = gate

    def fetch_company_news(self, symbol, cutoff, retrieved_at, lookback_days, limit):
        self.gate.wait(timeout=30)
        raise RuntimeError(SECRET)


def test_news_timeout_log_names_the_provider(monkeypatch, caplog) -> None:
    monkeypatch.setattr(data_stage, "ROLE_WAIT_MARGIN_SECONDS", 0.1)
    gate = threading.Event()
    try:
        with caplog.at_level(logging.DEBUG):
            _collect(
                _set(news=(StubNews("alpaca"), HangingNews(gate))),
                role_timeout_seconds=0.2,
            )
    finally:
        gate.set()

    lines = [r.getMessage() for r in caplog.records]
    assert "provider_role_failed role=news error=Timeout provider=slowwire" in lines
    assert SECRET not in caplog.text


def test_news_exception_log_names_the_provider_not_the_error_text(caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        _collect(_set(news=(StubNews("finnhub", error=RuntimeError(SECRET)),)))

    lines = [r.getMessage() for r in caplog.records]
    assert "provider_role_failed role=news error=RuntimeError provider=finnhub" in lines
    assert SECRET not in caplog.text


class FailingFundamentals(StubFundamentals):
    def fetch_fundamentals(self, symbol, retrieved_at, *, cutoff=None):
        raise TimeoutError(SECRET)


def test_fundamentals_failing_alone_leaves_filings_usable() -> None:
    out = _collect(_set(fundamentals=FailingFundamentals()))

    assert out.inputs.failed == {"fundamentals": "FILINGS_PROVIDER_FAILED"}
    assert out.inputs.filings is not None
    assert out.inputs.role_quality("filings") == RoleQuality.FRESH
    assert out.inputs.role_quality("fundamentals") == RoleQuality.FAILED
