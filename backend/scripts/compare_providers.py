"""Compare Alpaca (and optionally Tiingo) daily bars against yfinance.

Run by hand before a stage changes the default market provider. It is never
imported by app code and never run in CI. From the backend root:

    uv run python -m scripts.compare_providers [--output report.md]

Run it as a module: invoking the file directly puts scripts/ rather than the
backend root on the import path, and fails with
ModuleNotFoundError: No module named 'app'.

The Alpaca keys must be set (ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY);
without them it prints "Alpaca keys are not set" to stderr and exits with 2.
Tiingo is optional: without TIINGO_API_KEY the report says the cross-check was
skipped. The yfinance and Alpaca providers are built by name, whatever
MARKET_PROVIDER is set to.

The report holds tickers, dates, numbers and fixed messages only.

Type checking: CI's mypy run covers only the app packages, so this script is
checked only by the manual run `uv run mypy app scripts/compare_providers.py`.
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
import sys
from typing import cast

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.domain.errors import VantageError
from app.domain.research import CrossCheckClose, DailyBar
from app.providers.contracts import MarketDataProvider, PriceCrossCheckProvider
from app.providers.registry import default_registry
from app.services.sessions import latest_completed_xnys_session, trailing_xnys_sessions

PARITY_TICKERS: tuple[str, ...] = (
    # large caps
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "JPM", "XOM", "JNJ", "PG", "KO",
    # recent splits (2024)
    "NVDA", "AVGO", "CMG", "WMT",
    # share class
    "BRK.B",
    # high dividend
    "T", "VZ", "O",
    # ADRs
    "TSM", "ASML", "BABA",
    # ETFs
    "SPY", "QQQ", "XLK",
    # small cap
    "PLUG",
)  # fmt: skip

CLOSE_BOUND_PCT = 0.5
CLOSE_SHARE_MIN = 0.99
RETURN_GAP_BOUND_PP = 0.5
DOLLAR_VOLUME_BOUND = 0.10


@dataclass(frozen=True)
class TickerResult:
    symbol: str
    deviations: list[float]
    return_gap_pp: float | None
    dollar_volume_gap: float | None
    crosscheck_deviations: list[float] | None
    error: str | None = None


@dataclass(frozen=True)
class ParityVerdict:
    passed: bool
    within_share: float
    max_return_gap_pp: float
    max_dollar_volume_gap: float
    failed_tickers: list[tuple[str, str]]


def _by_date(bars: list[DailyBar]) -> dict[date, DailyBar]:
    return {b.session_date: b for b in bars}


def _common(a: list[DailyBar], b: list[DailyBar]) -> list[date]:
    return sorted(_by_date(a).keys() & _by_date(b).keys())


def _pct_dev(x: float | None, y: float | None) -> float | None:
    if x is None or y is None or x <= 0 or y <= 0:
        return None
    return abs(x - y) / y * 100


def close_deviations(a: list[DailyBar], b: list[DailyBar]) -> list[float]:
    """Absolute percent deviation of adjusted_close on dates present in both."""
    da, db = _by_date(a), _by_date(b)
    out: list[float] = []
    for day in sorted(da.keys() & db.keys()):
        dev = _pct_dev(da[day].adjusted_close, db[day].adjusted_close)
        if dev is not None:
            out.append(dev)
    return out


def crosscheck_deviations(
    bars: list[DailyBar], closes: list[CrossCheckClose]
) -> list[float]:
    """Absolute percent deviation of bar adjusted_close against cross-check closes."""
    by_bar = _by_date(bars)
    by_close = {c.session_date: c for c in closes}
    out: list[float] = []
    for day in sorted(by_bar.keys() & by_close.keys()):
        dev = _pct_dev(by_bar[day].adjusted_close, by_close[day].adjusted_close)
        if dev is not None:
            out.append(dev)
    return out


def return_gap_pp(a: list[DailyBar], b: list[DailyBar]) -> float:
    """Absolute difference, in percentage points, of the return over common dates."""
    days = _common(a, b)
    if len(days) < 2:
        raise ValueError("fewer than 2 common dates")
    da, db = _by_date(a), _by_date(b)

    def ret(by: dict[date, DailyBar]) -> float:
        return (by[days[-1]].adjusted_close / by[days[0]].adjusted_close - 1) * 100

    return abs(ret(da) - ret(db))


def dollar_volume_gap(a: list[DailyBar], b: list[DailyBar]) -> float:
    """Relative difference of the mean close * volume over common dates."""
    days = _common(a, b)
    if not days:
        raise ValueError("no common dates")
    da, db = _by_date(a), _by_date(b)
    mean_a = sum(da[d].close * da[d].volume for d in days) / len(days)
    mean_b = sum(db[d].close * db[d].volume for d in days) / len(days)
    if mean_b == 0:
        raise ValueError("reference dollar volume is zero")
    return abs(mean_a - mean_b) / mean_b


def evaluate(results: Sequence[TickerResult]) -> ParityVerdict:
    """Apply the inclusive bounds. A ticker that failed to fetch fails the verdict."""
    failed: list[tuple[str, str]] = []
    total = 0
    within = 0
    max_gap = 0.0
    max_dollar = 0.0
    for r in results:
        if (
            r.error is not None
            or r.return_gap_pp is None
            or r.dollar_volume_gap is None
        ):
            failed.append((r.symbol, "fetch failed"))
            continue
        total += len(r.deviations)
        within += sum(1 for d in r.deviations if d <= CLOSE_BOUND_PCT)
        max_gap = max(max_gap, r.return_gap_pp)
        max_dollar = max(max_dollar, r.dollar_volume_gap)
        if r.return_gap_pp > RETURN_GAP_BOUND_PP:
            failed.append((r.symbol, f"return gap above {RETURN_GAP_BOUND_PP} pp"))
        if r.dollar_volume_gap > DOLLAR_VOLUME_BOUND:
            failed.append(
                (r.symbol, f"dollar volume gap above {DOLLAR_VOLUME_BOUND:.0%}")
            )
    share = within / total if total else 0.0
    passed = not failed and total > 0 and share >= CLOSE_SHARE_MIN
    return ParityVerdict(
        passed=passed,
        within_share=share,
        max_return_gap_pp=max_gap,
        max_dollar_volume_gap=max_dollar,
        failed_tickers=failed,
    )


def _compare_ticker(
    symbol: str,
    reference: MarketDataProvider,
    candidate: MarketDataProvider,
    crosscheck: PriceCrossCheckProvider | None,
    start: date,
    end: date,
    now: datetime,
) -> TickerResult:
    try:
        ref_bars = reference.fetch_daily_snapshot(symbol, start, end, now).bars
        cand_bars = candidate.fetch_daily_snapshot(symbol, start, end, now).bars
        cross: list[float] | None = None
        if crosscheck is not None:
            snap = crosscheck.fetch_adjusted_closes(symbol, start, end, now)
            cross = crosscheck_deviations(cand_bars, snap.closes)
        return TickerResult(
            symbol=symbol,
            deviations=close_deviations(cand_bars, ref_bars),
            return_gap_pp=return_gap_pp(cand_bars, ref_bars),
            dollar_volume_gap=dollar_volume_gap(cand_bars, ref_bars),
            crosscheck_deviations=cross,
        )
    except VantageError as err:
        return TickerResult(symbol, [], None, None, None, err.safe_message)
    except ValueError:
        return TickerResult(
            symbol, [], None, None, None, "Too few matching sessions to compare."
        )


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_report(
    results: Sequence[TickerResult],
    verdict: ParityVerdict,
    start: date,
    end: date,
    crosscheck_ran: bool,
) -> str:
    lines = [
        "# Provider parity report",
        "",
        f"Window: {start.isoformat()} to {end.isoformat()}. "
        "Candidate: Alpaca. Reference: yfinance.",
        "",
        "| Ticker | Bars compared | Max close dev % | Return gap pp "
        "| Dollar volume gap | Cross-check max dev % | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        cross = (
            _fmt(max(r.crosscheck_deviations, default=None))
            if r.crosscheck_deviations is not None
            else "n/a"
        )
        lines.append(
            f"| {r.symbol} | {len(r.deviations)} "
            f"| {_fmt(max(r.deviations, default=None))} "
            f"| {_fmt(r.return_gap_pp)} | {_fmt(r.dollar_volume_gap, 4)} "
            f"| {cross} | {r.error or ''} |"
        )
    lines += ["", "## Verdict", ""]
    lines.append(
        "Overall: " + ("within bounds." if verdict.passed else "outside bounds.")
    )
    lines += [
        f"- Share of bars within {CLOSE_BOUND_PCT}% of the reference: "
        f"{verdict.within_share:.4f} (bound {CLOSE_SHARE_MIN}).",
        f"- Largest return gap: {verdict.max_return_gap_pp:.3f} pp "
        f"(bound {RETURN_GAP_BOUND_PP} pp).",
        f"- Largest dollar volume gap: {verdict.max_dollar_volume_gap:.4f} "
        f"(bound {DOLLAR_VOLUME_BOUND}).",
    ]
    for symbol, bound in verdict.failed_tickers:
        lines.append(f"- {symbol}: outside bounds ({bound}).")
    if not crosscheck_ran:
        lines.append("- Tiingo cross-check skipped: Tiingo is not configured.")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None, *, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider parity report")
    parser.add_argument("--output", help="write the report to this path")
    args = parser.parse_args(argv)
    cfg = settings or default_settings

    if not (cfg.ALPACA_API_KEY_ID and cfg.ALPACA_API_SECRET_KEY):
        print("Alpaca keys are not set", file=sys.stderr)
        return 2

    registry = default_registry()
    reference = cast(MarketDataProvider, registry.build("market", "yfinance", cfg))
    candidate = cast(MarketDataProvider, registry.build("market", "alpaca", cfg))
    crosscheck = cast(
        PriceCrossCheckProvider | None, registry.build("crosscheck", "tiingo", cfg)
    )

    now = datetime.now(UTC)
    end = latest_completed_xnys_session(now)
    start = trailing_xnys_sessions(end)[0]

    results = [
        _compare_ticker(s, reference, candidate, crosscheck, start, end, now)
        for s in PARITY_TICKERS
    ]
    verdict = evaluate(results)
    report = render_report(results, verdict, start, end, crosscheck is not None)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
