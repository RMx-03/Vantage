"""Research Workbench simulation engine (ADR-0008). Pure numpy, no I/O.

``run_experiment`` turns a spec and its frozen inputs into a result: the
full-period simulation, cost stress, the benchmark, optional walk-forward,
findings and a hash over all of it. Nothing here is advice or an order.
"""

import bisect
import hashlib
import json
from datetime import date

import numpy as np

from app.backtest.engine import simulate
from app.backtest.inputs import HistoryInputs
from app.backtest.metrics import METRICS_VERSION, compute_metrics, liquidity_findings
from app.backtest.templates import benchmark_targets, targets
from app.backtest.walk_forward import series_of, walk_forward
from app.domain.experiments import (
    CostStress,
    ExperimentResult,
    ExperimentSpec,
    Finding,
    SimulatedTrade,
)
from app.domain.research import ResearchStatus

ENGINE_VERSION = "backtest-engine-v1"
# A busy 50-name run makes ~67k fills; storing them all costs ~9 MB per result.
MAX_STORED_TRADES = 10_000
MIN_EVAL_SESSIONS = 21
MAX_MISSING_SHARE = 0.05
COST_MULTIPLIERS = (0.5, 1.0, 2.0)


class ExperimentDataError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        symbol: str | None = None,
        last_session: date | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.symbol = symbol
        self.last_session = last_session


def validate_inputs(inputs: HistoryInputs) -> list[Finding]:
    """Fail on unusable history; report tolerable gaps as findings."""
    dates = inputs.session_dates
    n = len(dates)
    findings = []
    for j, name in enumerate(inputs.names):
        valid = ~np.isnan(inputs.close_adj[:, j])
        if not valid.any():
            raise ExperimentDataError(
                "SYMBOL_NOT_FOUND", f"No daily bars were returned for {name}.", name
            )
        present = np.flatnonzero(valid)
        first, last = int(present[0]), int(present[-1])
        if last < n - 1:
            raise ExperimentDataError(
                "INSTRUMENT_DATA_ENDED",
                f"{name} has no bars after {dates[last]}; the simulation will not "
                "assume an exit at its last quote. Remove it or end earlier.",
                name,
                dates[last],
            )
        missing = int((~valid[first:]).sum())
        if missing / (n - first) > MAX_MISSING_SHARE:
            raise ExperimentDataError(
                "INSUFFICIENT_HISTORY",
                f"{name} is missing {missing} of {n - first} sessions.",
                name,
            )
        if first > 0:
            findings.append(
                Finding(
                    code="INSTRUMENT_STARTS_LATE",
                    message=f"{name} has bars only from {dates[first]}; it is "
                    "ineligible until its own warm-up completes.",
                    symbol=name,
                )
            )
        if missing:
            findings.append(
                Finding(
                    code="MISSING_SESSIONS",
                    message=f"{name} has {missing} missing session(s); holdings "
                    "were valued at the last close and fills waited for an open.",
                    symbol=name,
                    count=missing,
                )
            )
    return findings


def with_hash(result: ExperimentResult) -> ExperimentResult:
    payload = result.model_dump(mode="json", exclude={"result_hash"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return result.model_copy(
        update={"result_hash": hashlib.sha256(canonical.encode()).hexdigest()}
    )


def run_experiment(spec: ExperimentSpec, inputs: HistoryInputs) -> ExperimentResult:
    dates = inputs.session_dates
    eval_start = bisect.bisect_left(dates, spec.start)
    first_decision = max(eval_start - 1, 0)
    findings = validate_inputs(inputs)
    if len(dates) - first_decision - 1 < MIN_EVAL_SESSIONS:
        return with_hash(
            ExperimentResult(
                research_status=ResearchStatus.INSUFFICIENT_DATA,
                engine_version=ENGINE_VERSION,
                metrics_version=METRICS_VERSION,
                findings=findings,
            )
        )

    rows = targets(spec.strategy, inputs, first_decision)
    ledgers = {
        m: simulate(rows, inputs, spec.cost_bps * m, record_trades=m == 1.0)
        for m in COST_MULTIPLIERS
    }
    main = ledgers[1.0]
    bench = simulate(
        benchmark_targets(inputs, first_decision),
        inputs,
        spec.cost_bps,
        record_trades=False,
    )
    findings += liquidity_findings(main, inputs)
    if not main.trades:
        findings.append(
            Finding(
                code="NO_SIMULATED_TRADES",
                message="No name became eligible for the template in this range; "
                "the simulation held cash throughout.",
            )
        )

    wf = walk_forward(spec, inputs, first_decision) if spec.candidates else None
    if wf is not None and wf.status == "insufficient_data":
        findings.append(
            Finding(
                code="WALK_FORWARD_INSUFFICIENT_DATA",
                message="Walk-forward needs at least 3 test windows (756 training "
                "plus 3 x 126 test sessions after warm-up).",
            )
        )

    series = series_of(main, dates, first_decision, len(dates))
    bench_nav = bench.nav[first_decision:]
    series.benchmark_nav = (
        bench_nav / bench_nav[0] * main.nav[first_decision]
    ).tolist()
    result = ExperimentResult(
        research_status=(
            ResearchStatus.REVIEW if findings else ResearchStatus.INFORMATIONAL
        ),
        engine_version=ENGINE_VERSION,
        metrics_version=METRICS_VERSION,
        metrics=compute_metrics(main, dates, start=first_decision),
        benchmark_metrics=compute_metrics(bench, dates, start=first_decision),
        series=series,
        trades=[
            SimulatedTrade(
                session=dates[t.session],
                symbol=inputs.names[t.name],
                shares=t.shares,
                price=t.price,
                notional=t.notional,
            )
            for t in main.trades[:MAX_STORED_TRADES]
        ],
        trade_count=len(main.trades),
        cost_stress=[
            CostStress(
                multiplier=m,
                cost_bps=spec.cost_bps * m,
                metrics=compute_metrics(ledgers[m], dates, start=first_decision),
            )
            for m in COST_MULTIPLIERS
        ],
        walk_forward=wf,
        findings=findings,
    )
    return with_hash(result)
