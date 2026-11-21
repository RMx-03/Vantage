"""Research Workbench experiment contracts (ADR-0008).

An experiment is a research-only simulation of one allowlisted template over a
user-chosen list of US equities. Nothing here is advice or an order.
"""

import hashlib
import json
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from app.domain.research import StrictModel, Symbol

MAX_SYMBOLS = 50
MAX_CANDIDATES = 12
MAX_TOP_K = 10
MAX_RANGE_DAYS = 3653  # ten calendar years, leap days included

SURVIVORSHIP_LABEL = "Exploratory: list chosen today, survivorship bias possible"


class BuyAndHoldParams(StrictModel):
    template: Literal["buy_and_hold"] = "buy_and_hold"


class SmaCrossoverParams(StrictModel):
    template: Literal["sma_crossover"] = "sma_crossover"
    fast: int = Field(ge=5, le=100)
    slow: int = Field(ge=20, le=250)

    @model_validator(mode="after")
    def fast_below_slow(self) -> Self:
        if self.fast >= self.slow:
            raise ValueError("fast must be shorter than slow")
        return self


class MomentumTopKParams(StrictModel):
    template: Literal["momentum_top_k"] = "momentum_top_k"
    lookback: Literal[126, 252]
    skip: Literal[21] = 21
    k: int = Field(ge=1, le=MAX_TOP_K)


StrategyParams = Annotated[
    BuyAndHoldParams | SmaCrossoverParams | MomentumTopKParams,
    Field(discriminator="template"),
]


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class ExperimentSpec(StrictModel):
    question: str = Field(min_length=1, max_length=500)
    hypothesis: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=4000)
    symbols: list[Symbol] = Field(min_length=1, max_length=MAX_SYMBOLS)
    benchmark: Symbol = "SPY"
    start: date
    end: date | None = None
    strategy: StrategyParams
    cost_bps: float = Field(default=10, ge=0, le=100)
    candidates: list[StrategyParams] = Field(
        default_factory=list, max_length=MAX_CANDIDATES
    )

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> object:
        return [_upper(v) for v in value] if isinstance(value, list) else value

    @field_validator("benchmark", mode="before")
    @classmethod
    def normalize_benchmark(cls, value: object) -> object:
        return _upper(value)

    @model_validator(mode="after")
    def check_consistency(self) -> Self:
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must be unique")
        if self.end is not None:
            if self.start >= self.end:
                raise ValueError("start must be before end")
            if (self.end - self.start).days > MAX_RANGE_DAYS:
                raise ValueError("the date range is limited to ten years")
        for params in (self.strategy, *self.candidates):
            if params.template != self.strategy.template:
                raise ValueError("candidates must use the strategy's template")
            if isinstance(params, MomentumTopKParams) and params.k > len(self.symbols):
                raise ValueError("k cannot exceed the number of symbols")
        return self

    def spec_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


class Finding(StrictModel):
    code: str
    message: str
    symbol: str | None = None
    count: int | None = None
