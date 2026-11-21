"""Experiment plan preview: what will run, without calling any provider."""

from datetime import date

from app.backtest.templates import warmup_sessions
from app.backtest.walk_forward import MIN_WINDOWS, build_windows
from app.domain.experiments import SURVIVORSHIP_LABEL, ExperimentPlan, ExperimentSpec
from app.services.sessions import XNYS


def fetch_warmup(spec: ExperimentSpec) -> int:
    """Sessions fetched before ``start`` so the first decision has full history."""
    return max(1, *(warmup_sessions(p) for p in (spec.strategy, *spec.candidates)))


def plan_experiment(
    spec: ExperimentSpec, default_end: date | None = None
) -> ExperimentPlan:
    end = spec.end or default_end
    if end is None:
        raise ValueError("an end session is required")
    sessions = XNYS.sessions_in_range(spec.start, end)
    warmup = fetch_warmup(spec)
    fetch_start = XNYS.sessions_window(sessions[0], -(warmup + 1))[0].date()
    n_candidates = len(spec.candidates)
    windows = (
        len(build_windows(len(sessions) + warmup, warmup - 1)) if n_candidates else 0
    )
    warnings = [SURVIVORSHIP_LABEL]
    if not n_candidates:
        warnings.append(
            "No candidates were given, so there is no walk-forward evaluation."
        )
    elif windows < MIN_WINDOWS:
        warnings.append(
            "The range is too short for walk-forward evaluation: it needs at least "
            "3 test windows (about 5.5 years of sessions after warm-up)."
        )
    return ExperimentPlan(
        end=end,
        fetch_start=fetch_start,
        sessions=len(sessions),
        warmup_sessions=warmup,
        windows=windows,
        candidates=n_candidates,
        engine_invocations=4 + (n_candidates + 1 if n_candidates else 0),
        warnings=warnings,
    )
