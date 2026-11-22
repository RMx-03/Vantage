from datetime import date, timedelta

import pytest

from app.backtest.plan import PlanRangeError, fetch_warmup, plan_experiment
from app.domain.experiments import SURVIVORSHIP_LABEL, ExperimentSpec
from app.services.sessions import XNYS


def _spec(**extra: object) -> ExperimentSpec:
    raw: dict[str, object] = {
        "question": "q",
        "symbols": ["AAPL", "MSFT", "NVDA"],
        "start": "2020-01-02",
        "end": "2024-12-31",
        "strategy": {"template": "momentum_top_k", "lookback": 252, "k": 2},
    }
    raw.update(extra)
    return ExperimentSpec.model_validate(raw)


def test_plan_counts_sessions_warmup_and_invocations_without_io() -> None:
    plan = plan_experiment(_spec())
    assert plan.end == date(2024, 12, 31)
    assert plan.sessions == 1258  # XNYS sessions 2020-01-02..2024-12-31
    assert plan.warmup_sessions == 253
    assert plan.fetch_start < date(2020, 1, 2)
    assert plan.windows == 0
    assert plan.candidates == 0
    assert plan.engine_invocations == 4  # three cost levels and the benchmark
    assert SURVIVORSHIP_LABEL in plan.warnings


def test_plan_counts_walk_forward_windows_and_candidates() -> None:
    plan = plan_experiment(
        _spec(
            candidates=[
                {"template": "momentum_top_k", "lookback": 252, "k": 1},
                {"template": "momentum_top_k", "lookback": 126, "k": 2},
            ]
        )
    )
    assert plan.candidates == 2
    assert plan.windows == (1258 + 1 - 756 - 126) // 126 + 1
    assert plan.engine_invocations == 4 + 2 + 1


def test_plan_warns_when_walk_forward_is_too_short() -> None:
    plan = plan_experiment(
        _spec(
            start="2023-01-03",
            candidates=[{"template": "momentum_top_k", "lookback": 126, "k": 1}],
        )
    )
    assert plan.windows < 3
    assert any("walk-forward" in w for w in plan.warnings)


def test_plan_resolves_a_missing_end_to_the_given_session() -> None:
    raw = _spec().model_dump(mode="json")
    raw["end"] = None
    plan = plan_experiment(
        ExperimentSpec.model_validate(raw), default_end=date(2024, 12, 31)
    )
    assert plan.end == date(2024, 12, 31)


def _range_spec(start: date, end: date, **strategy: object) -> ExperimentSpec:
    return ExperimentSpec(
        question="Does the plan explain an unusable range?",
        symbols=["AAA", "BBB", "CCC"],
        start=start,
        end=end,
        strategy=strategy or {"template": "buy_and_hold"},
    )


def test_a_range_without_sessions_is_explained() -> None:
    # Good Friday to Easter Sunday 2024: no trading session at all.
    with pytest.raises(PlanRangeError, match="no trading sessions"):
        plan_experiment(_range_spec(date(2024, 3, 29), date(2024, 3, 31)))


def test_a_start_before_the_calendar_is_explained() -> None:
    first = XNYS.first_session.date()
    with pytest.raises(PlanRangeError, match="on or after"):
        plan_experiment(
            _range_spec(first - timedelta(days=400), first + timedelta(days=30))
        )


def test_a_start_without_room_for_warm_up_names_the_earliest_start() -> None:
    first = XNYS.first_session.date()
    spec = _range_spec(
        first + timedelta(days=10),
        first + timedelta(days=900),
        template="momentum_top_k",
        lookback=252,
        k=2,
    )
    earliest = XNYS.sessions[fetch_warmup(spec)].date()
    with pytest.raises(PlanRangeError, match=earliest.isoformat()):
        plan_experiment(spec)
    assert (
        plan_experiment(spec.model_copy(update={"start": earliest})).fetch_start
        == first
    )
