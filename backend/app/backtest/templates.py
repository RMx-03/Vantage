"""Allowlisted strategy templates (ADR-0008). Targets only, never orders.

``targets`` returns weights per session x name (benchmark column always 0).
A row is a decision at that close; NaN rows mean "no new decision". Every
value at row t depends only on closes up to t, and a name is eligible only
after its own warm-up, so later data and later listings never leak backwards.
"""

import numpy as np

from app.backtest.inputs import HistoryInputs
from app.domain.experiments import (
    BuyAndHoldParams,
    MomentumTopKParams,
    SmaCrossoverParams,
)

Params = BuyAndHoldParams | SmaCrossoverParams | MomentumTopKParams


def warmup_sessions(params: Params) -> int:
    if isinstance(params, SmaCrossoverParams):
        return params.slow
    if isinstance(params, MomentumTopKParams):
        return params.lookback + 1
    return 0


def month_ends(sessions: np.ndarray) -> np.ndarray:
    """True on each month's last session; the final session is never marked."""
    months = sessions.astype("datetime64[M]")
    mask = np.zeros(len(sessions), dtype=bool)
    mask[:-1] = months[:-1] != months[1:]
    return mask


def _ffill(values: np.ndarray) -> np.ndarray:
    idx = np.where(np.isnan(values), 0, np.arange(len(values))[:, None])
    np.maximum.accumulate(idx, axis=0, out=idx)
    filled = values[idx, np.arange(values.shape[1])]
    return filled


def _age(closes: np.ndarray) -> np.ndarray:
    """Sessions since each name's first close, counting that session (0 before)."""
    listed = np.maximum.accumulate(~np.isnan(closes), axis=0)
    return np.cumsum(listed, axis=0)


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    csum = np.cumsum(np.nan_to_num(values), axis=0)
    out = np.full(values.shape, np.nan)
    out[window - 1] = csum[window - 1] / window
    out[window:] = (csum[window:] - csum[:-window]) / window
    return out


def benchmark_targets(inputs: HistoryInputs, first_decision: int) -> np.ndarray:
    out = np.full(inputs.close_adj.shape, np.nan)
    out[first_decision] = 0.0
    out[first_decision, inputs.benchmark_index] = 1.0
    return out


def targets(params: Params, inputs: HistoryInputs, first_decision: int) -> np.ndarray:
    closes = inputs.close_adj
    n_sessions, n_names = closes.shape
    n_symbols = len(inputs.symbols)
    out = np.full((n_sessions, n_names), np.nan)
    age = _age(closes)[:, :n_symbols]

    if isinstance(params, BuyAndHoldParams):
        listed = age[first_decision] > 0
        out[first_decision] = 0.0
        if listed.any():
            out[first_decision, :n_symbols] = listed / listed.sum()
        return out

    filled = _ffill(closes)[:, :n_symbols]

    if isinstance(params, SmaCrossoverParams):
        if n_sessions < params.slow:
            return out
        eligible = age >= params.slow
        fast = _rolling_mean(filled, params.fast)
        slow = _rolling_mean(filled, params.slow)
        held = eligible & (np.nan_to_num(fast) > np.nan_to_num(slow))
        previous: np.ndarray | None = None
        for t in range(first_decision, n_sessions):
            if not eligible[t].any():
                continue
            count = held[t].sum()
            row = held[t] / count if count else np.zeros(n_symbols)
            if previous is None or not np.array_equal(row, previous):
                out[t] = 0.0
                out[t, :n_symbols] = row
                previous = row
        return out

    ends = month_ends(inputs.sessions)
    need = warmup_sessions(params)
    for t in range(max(first_decision, params.lookback), n_sessions):
        eligible = age[t] >= need
        if not ends[t] or not eligible.any():
            continue
        score = filled[t - params.skip] / filled[t - params.lookback] - 1
        candidates = np.flatnonzero(eligible)
        order = candidates[np.lexsort((candidates, -score[candidates]))]
        out[t] = 0.0
        out[t, order[: params.k]] = 1.0 / params.k
    return out
