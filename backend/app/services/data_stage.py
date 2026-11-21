"""The data stage: collect every data role for one research run.

Filings come first because their SIC code picks the sector ETF the market role also
fetches. Market prices, each news provider, fundamentals, macro and the price
cross-check then run concurrently, each group capped in time. Only the market role can
fail the run; every other role turns a failure, a slow call or a missing provider into a
visible state.

This module takes no settings object and reads no environment: everything arrives as
arguments.
"""

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime
import logging
import time
from typing import Any, Literal, cast

from opentelemetry import context as otel_context

from app.domain.errors import VantageError
from app.domain.research import (
    ComponentQuality,
    FilingsSnapshot,
    FundamentalsSnapshot,
    MacroSnapshot,
    MarketSnapshot,
    NewsSnapshot,
    PriceCrossCheckSnapshot,
    ProviderRecord,
    RoleQuality,
)
from app.providers.contracts import NewsProvider
from app.providers.registry import ProviderSet
from app.services.evidence import merge_news
from app.services.run_inputs import OPTIONAL_ROLES, RunInputs
from app.services.sectors import sic_to_sector_etf
from app.services.sessions import market_snapshot_hash
from app.telemetry.tracing import get_tracer

logger = logging.getLogger(__name__)

FILING_LOOKBACK_DAYS = 30
NEWS_ITEM_LIMIT = 10
ROLE_WAIT_MARGIN_SECONDS = 2.0
MARKET_CONTEXT_SYMBOL = "SPY"

_FAILURE_CODES = {
    "filings": "FILINGS_PROVIDER_FAILED",
    "fundamentals": "FILINGS_PROVIDER_FAILED",
    "macro": "MACRO_PROVIDER_FAILED",
    "crosscheck": "PRICE_CROSSCHECK_FAILED",
}
_NEWS_FAILURE_CODE = "NEWS_PROVIDER_FAILED"
_NO_FILER_RECORD = "NO_SEC_FILER_RECORD"

Role = Literal["market", "news", "filings", "fundamentals", "macro", "crosscheck"]


@dataclass(frozen=True)
class CollectedInputs:
    market: MarketSnapshot
    news: NewsSnapshot
    inputs: RunInputs
    records: list[ProviderRecord]


class _Timeout:
    """Marks a worker still running when its wait cap passed."""


_TIMEOUT = _Timeout()


def _log_failure(role: str, error: str, provider: str | None = None) -> None:
    # `provider` is a provider's fixed class-level name, never an exception text.
    if provider is None:
        logger.warning("provider_role_failed role=%s error=%s", role, error)
    else:
        logger.warning(
            "provider_role_failed role=%s error=%s provider=%s", role, error, provider
        )


def _log_exception(role: str, exc: BaseException, provider: str | None = None) -> None:
    # Only the type name: an exception message may carry provider data.
    if not isinstance(exc, VantageError):
        _log_failure(role, type(exc).__name__, provider)


def _run_tasks(
    tasks: dict[str, Callable[[], Any]], cap: float
) -> dict[str, Future[Any] | _Timeout]:
    """Run tasks on one per-call pool and wait for all of them under one deadline.

    Returns each key's finished future, or ``_TIMEOUT`` when it was still running at the
    deadline. The pool is never joined, so a hung worker cannot hold the run.
    """
    executor = ThreadPoolExecutor(max_workers=max(1, len(tasks)))
    deadline = time.monotonic() + cap
    try:
        futures = {key: executor.submit(task) for key, task in tasks.items()}
        done, _ = wait(
            list(futures.values()), timeout=max(0.0, deadline - time.monotonic())
        )
        return {
            key: (future if future in done else _TIMEOUT)
            for key, future in futures.items()
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _worker(
    ctx: otel_context.Context,
    role: str,
    provider_name: str,
    run_id: str,
    call: Callable[[], Any],
    after: Callable[[], None] | None = None,
) -> Callable[[], Any]:
    """Wrap a provider call in its spans, attached to the caller's trace context."""

    def run() -> Any:
        token = otel_context.attach(ctx)
        try:
            tracer = get_tracer()
            with tracer.start_as_current_span(f"fetch_{role}_snapshot") as role_span:
                role_span.set_attribute("vantage.run_id", run_id)
                with tracer.start_as_current_span("provider_request") as p_span:
                    p_span.set_attribute("vantage.run_id", run_id)
                    p_span.set_attribute("vantage.provider.role", role)
                    p_span.set_attribute("vantage.provider.name", provider_name)
                    result = call()
                if after is not None:
                    after()
                return result
        finally:
            otel_context.detach(token)

    return run


def collect_inputs(
    providers: ProviderSet,
    *,
    symbol: str,
    now: datetime,
    cutoff: datetime,
    sessions: Sequence[date],
    news_lookback_days: int,
    role_timeout_seconds: float,
    run_id: str,
) -> CollectedInputs:
    market_provider = providers.market
    if market_provider is None:
        raise VantageError(
            code="MARKET_DATA_PROVIDER_FAILED",
            safe_message="Market data provider is not configured.",
        )

    cap = role_timeout_seconds + ROLE_WAIT_MARGIN_SECONDS
    ctx = otel_context.get_current()
    failed: dict[str, str] = {}
    start_session, end_session = sessions[0], sessions[-1]

    # 1. Filings first: their SIC code picks the sector ETF.
    filings: FilingsSnapshot | None = None
    sector_etf: str | None = None
    if providers.filings is not None:
        filings_provider = providers.filings
        outcome = _run_tasks(
            {
                "filings": _worker(
                    ctx,
                    "filings",
                    filings_provider.name,
                    run_id,
                    lambda: filings_provider.fetch_filing_evidence(
                        symbol, cutoff, now, FILING_LOOKBACK_DAYS
                    ),
                )
            },
            cap,
        )["filings"]
        if isinstance(outcome, _Timeout):
            _log_failure("filings", "Timeout")
            failed["filings"] = _FAILURE_CODES["filings"]
        elif (exc := outcome.exception()) is not None:
            _log_exception("filings", exc)
            failed["filings"] = (
                exc.code if isinstance(exc, VantageError) else _FAILURE_CODES["filings"]
            )
        else:
            filings = outcome.result()
            if filings.quality != ComponentQuality.FAILED and filings.sic_code:
                sector_etf = sic_to_sector_etf(filings.sic_code)

    # 2. Everything else, concurrently under one shared deadline.
    context_symbols = (MARKET_CONTEXT_SYMBOL,) + (
        (sector_etf,) if sector_etf and sector_etf != MARKET_CONTEXT_SYMBOL else ()
    )

    def fetch_market() -> MarketSnapshot:
        try:
            snapshot = market_provider.fetch_daily_snapshot(
                symbol,
                start_session,
                end_session,
                now,
                context_symbols=context_symbols,
            )
        except VantageError as exc:
            if exc.code != "INVALID_PRICE_SERIES":
                raise
            snapshot = MarketSnapshot(
                symbol=symbol,
                bars=[],
                provider=market_provider.name,
                retrieved_at=now,
                as_of=cutoff,
                latest_completed_session=end_session,
                content_hash=market_snapshot_hash(symbol, []),
                quality=ComponentQuality.FAILED,
                error_code="INVALID_PRICE_SERIES",
                missing_value_count=exc.missing_value_count,
                duplicate_session_count=exc.duplicate_session_count,
            )
        return snapshot.model_copy(
            update={"as_of": cutoff, "latest_completed_session": end_session}
        )

    def validate_prices() -> None:
        with get_tracer().start_as_current_span("validate_price_quality") as span:
            span.set_attribute("vantage.run_id", run_id)

    tasks: dict[str, Callable[[], Any]] = {
        "market": _worker(
            ctx, "market", market_provider.name, run_id, fetch_market, validate_prices
        )
    }

    def news_call(provider: NewsProvider) -> Callable[[], NewsSnapshot]:
        return lambda: provider.fetch_company_news(
            symbol, cutoff, now, news_lookback_days, NEWS_ITEM_LIMIT
        )

    for index, news_provider in enumerate(providers.news):
        tasks[f"news:{index}"] = _worker(
            ctx, "news", news_provider.name, run_id, news_call(news_provider)
        )

    fundamentals: FundamentalsSnapshot | None = None
    if providers.fundamentals is not None:
        fundamentals_provider = providers.fundamentals
        filings_error = failed.get("filings") or (
            (filings.error_code or _FAILURE_CODES["filings"])
            if filings is not None and filings.quality == ComponentQuality.FAILED
            else None
        )
        if filings_error is not None:
            failed["fundamentals"] = filings_error
        elif (
            filings is not None
            and filings.quality == ComponentQuality.MISSING
            and filings.error_code == _NO_FILER_RECORD
        ):
            fundamentals = FundamentalsSnapshot(
                symbol=symbol,
                provider=fundamentals_provider.name,
                retrieved_at=now,
                quality=ComponentQuality.MISSING,
                error_code=_NO_FILER_RECORD,
            )
        else:
            tasks["fundamentals"] = _worker(
                ctx,
                "fundamentals",
                fundamentals_provider.name,
                run_id,
                lambda: fundamentals_provider.fetch_fundamentals(
                    symbol, now, cutoff=cutoff
                ),
            )
    if providers.macro is not None:
        macro_provider = providers.macro
        tasks["macro"] = _worker(
            ctx,
            "macro",
            macro_provider.name,
            run_id,
            lambda: macro_provider.fetch_macro(end_session, now),
        )
    if providers.crosscheck is not None:
        crosscheck_provider = providers.crosscheck
        tasks["crosscheck"] = _worker(
            ctx,
            "crosscheck",
            crosscheck_provider.name,
            run_id,
            lambda: crosscheck_provider.fetch_adjusted_closes(
                symbol, start_session, end_session, now
            ),
        )

    outcomes = _run_tasks(tasks, cap)

    # Market: today's semantics. Anything but a timeout propagates as it is.
    market_outcome = outcomes["market"]
    if isinstance(market_outcome, _Timeout):
        _log_failure("market", "Timeout")
        raise VantageError(
            code="MARKET_DATA_PROVIDER_FAILED",
            safe_message="Market prices could not be retrieved.",
        )
    market = cast(MarketSnapshot, market_outcome.result())

    # News: a failed provider becomes a failed snapshot; the merge stays partial.
    if not providers.news:
        with get_tracer().start_as_current_span("fetch_news_snapshot") as n_span:
            n_span.set_attribute("vantage.run_id", run_id)
            with get_tracer().start_as_current_span("provider_request") as p_span:
                p_span.set_attribute("vantage.run_id", run_id)
                news = NewsSnapshot(
                    symbol=symbol,
                    items=[],
                    provider="none",
                    retrieved_at=now,
                    quality=ComponentQuality.FAILED,
                    error_code=_NEWS_FAILURE_CODE,
                )
    else:
        news_snapshots: list[NewsSnapshot] = []
        for index, news_provider in enumerate(providers.news):
            news_outcome = outcomes[f"news:{index}"]
            code = _NEWS_FAILURE_CODE
            if isinstance(news_outcome, _Timeout):
                _log_failure("news", "Timeout", news_provider.name)
            elif (exc := news_outcome.exception()) is not None:
                _log_exception("news", exc, news_provider.name)
                if isinstance(exc, VantageError):
                    code = exc.code
            else:
                news_snapshots.append(news_outcome.result())
                continue
            news_snapshots.append(
                NewsSnapshot(
                    symbol=symbol,
                    items=[],
                    provider=news_provider.name,
                    retrieved_at=now,
                    quality=ComponentQuality.FAILED,
                    error_code=code,
                )
            )
        news = merge_news(news_snapshots, symbol=symbol, limit=NEWS_ITEM_LIMIT)
    with get_tracer().start_as_current_span("validate_news_quality") as v_span:
        v_span.set_attribute("vantage.run_id", run_id)

    # Optional roles: any failure or timeout is a visible failed state.
    def optional(role: str) -> Any:
        outcome = outcomes.get(role)
        if outcome is None:
            return None
        if isinstance(outcome, _Timeout):
            _log_failure(role, "Timeout")
            failed[role] = _FAILURE_CODES[role]
            return None
        exc = outcome.exception()
        if exc is not None:
            _log_exception(role, exc)
            failed[role] = (
                exc.code if isinstance(exc, VantageError) else _FAILURE_CODES[role]
            )
            return None
        return outcome.result()

    if "fundamentals" in outcomes:
        fundamentals = optional("fundamentals")
    macro: MacroSnapshot | None = optional("macro")
    crosscheck: PriceCrossCheckSnapshot | None = optional("crosscheck")

    not_configured = frozenset(
        role for role in OPTIONAL_ROLES if getattr(providers, role) is None
    )
    inputs = RunInputs(
        filings=filings,
        fundamentals=fundamentals,
        macro=macro,
        crosscheck=crosscheck,
        sector_etf=sector_etf,
        failed=failed,
        not_configured=not_configured,
    )

    records: list[ProviderRecord] = [
        ProviderRecord(
            role="market",
            provider=market.provider,
            retrieved_at=market.retrieved_at,
            quality=RoleQuality(market.quality.value),
            error_code=market.error_code,
            content_hash=market.content_hash,
        ),
        ProviderRecord(
            role="news",
            provider=news.provider,
            retrieved_at=news.retrieved_at,
            quality=RoleQuality(news.quality.value),
            error_code=news.error_code,
        )
        if providers.news
        else ProviderRecord(
            role="news",
            provider=None,
            retrieved_at=None,
            quality=RoleQuality.NOT_CONFIGURED,
        ),
    ]
    for role in OPTIONAL_ROLES:
        records.append(_optional_record(role, providers, inputs, now))
    return CollectedInputs(market=market, news=news, inputs=inputs, records=records)


def _optional_record(
    role: str, providers: ProviderSet, inputs: RunInputs, now: datetime
) -> ProviderRecord:
    typed_role = cast(Role, role)
    provider = getattr(providers, role)
    if provider is None:
        return ProviderRecord(
            role=typed_role,
            provider=None,
            retrieved_at=None,
            quality=RoleQuality.NOT_CONFIGURED,
        )
    if role in inputs.failed:
        return ProviderRecord(
            role=typed_role,
            provider=provider.name,
            retrieved_at=now,
            quality=RoleQuality.FAILED,
            error_code=inputs.failed[role],
        )
    snapshot = getattr(inputs, role)
    assert snapshot is not None
    return ProviderRecord(
        role=typed_role,
        provider=provider.name,
        retrieved_at=snapshot.retrieved_at,
        quality=RoleQuality(snapshot.quality.value),
        error_code=snapshot.error_code,
    )
