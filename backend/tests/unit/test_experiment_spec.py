from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.experiments import ExperimentSpec


def _spec(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "question": "Did momentum hold up after costs?",
        "symbols": ["AAPL", "MSFT"],
        "start": "2018-01-02",
        "end": "2024-12-31",
        "strategy": {"template": "buy_and_hold"},
    }
    base.update(overrides)
    return base


def test_minimal_spec_gets_defaults() -> None:
    spec = ExperimentSpec.model_validate(_spec())
    assert spec.benchmark == "SPY"
    assert spec.cost_bps == 10
    assert spec.candidates == []
    assert spec.end == date(2024, 12, 31)


def test_symbols_are_normalised_like_research_requests() -> None:
    spec = ExperimentSpec.model_validate(
        _spec(symbols=[" aapl ", "brk.b"], benchmark=" qqq")
    )
    assert spec.symbols == ["AAPL", "BRK.B"]
    assert spec.benchmark == "QQQ"


@pytest.mark.parametrize(
    "overrides",
    [
        {"unexpected": 1},
        {"symbols": []},
        {"symbols": [f"S{i}" for i in range(51)]},
        {"symbols": ["AAPL", "aapl"]},
        {"symbols": ["NOT A TICKER"]},
        {"cost_bps": -1},
        {"cost_bps": 101},
        {"start": "2024-12-31", "end": "2024-12-31"},
        {"start": "2010-01-04", "end": "2024-12-31"},
        {"question": ""},
        {"question": "x" * 501},
        {"strategy": {"template": "sma_crossover", "fast": 50, "slow": 50}},
        {"strategy": {"template": "sma_crossover", "fast": 4, "slow": 50}},
        {"strategy": {"template": "sma_crossover", "fast": 20, "slow": 251}},
        {"strategy": {"template": "momentum_top_k", "lookback": 200, "k": 1}},
        {"strategy": {"template": "momentum_top_k", "lookback": 252, "k": 3}},
        {"strategy": {"template": "custom_code"}},
        {"candidates": [{"template": "buy_and_hold"}] * 13},
        {
            "strategy": {"template": "buy_and_hold"},
            "candidates": [{"template": "sma_crossover", "fast": 10, "slow": 50}],
        },
    ],
)
def test_invalid_specs_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(_spec(**overrides))


def test_momentum_k_is_bounded_by_ten_and_symbol_count() -> None:
    symbols = [f"S{i}" for i in range(12)]
    ok = _spec(
        symbols=symbols,
        strategy={"template": "momentum_top_k", "lookback": 126, "k": 10},
    )
    assert ExperimentSpec.model_validate(ok).strategy.k == 10  # type: ignore[union-attr]
    too_big = _spec(
        symbols=symbols,
        strategy={"template": "momentum_top_k", "lookback": 126, "k": 11},
    )
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(too_big)


def test_candidates_share_the_strategy_template() -> None:
    spec = ExperimentSpec.model_validate(
        _spec(
            strategy={"template": "sma_crossover", "fast": 20, "slow": 100},
            candidates=[
                {"template": "sma_crossover", "fast": 10, "slow": 50},
                {"template": "sma_crossover", "fast": 50, "slow": 200},
            ],
        )
    )
    assert len(spec.candidates) == 2


def test_end_may_be_omitted_and_resolved_later() -> None:
    raw = _spec()
    del raw["end"]
    assert ExperimentSpec.model_validate(raw).end is None


def test_spec_hash_is_stable_and_sensitive() -> None:
    a = ExperimentSpec.model_validate(_spec())
    b = ExperimentSpec.model_validate(_spec())
    c = ExperimentSpec.model_validate(_spec(cost_bps=11))
    assert a.spec_hash() == b.spec_hash()
    assert a.spec_hash() != c.spec_hash()
