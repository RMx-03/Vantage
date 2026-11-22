"""Frozen simulation inputs: everything an experiment computed from, in one hashable blob.

Columns are the experiment's symbols followed by the benchmark. Prices are
total-return adjusted (splits and dividends inside the series); dollar volume
is raw close times raw volume. NaN marks a session with no bar for that name.
"""

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np


@dataclass(frozen=True)
class HistoryInputs:
    symbols: tuple[str, ...]
    benchmark: str
    sessions: np.ndarray  # datetime64[D], strictly increasing
    open_adj: np.ndarray  # float64, sessions x names
    close_adj: np.ndarray
    dollar_volume: np.ndarray
    provider: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        shape = (len(self.sessions), len(self.symbols) + 1)
        for name in ("open_adj", "close_adj", "dollar_volume"):
            if getattr(self, name).shape != shape:
                raise ValueError(f"{name} must have shape {shape}")
        if len(self.sessions) > 1 and not bool(
            np.all(np.diff(self.sessions) > np.timedelta64(0, "D"))
        ):
            raise ValueError("sessions must be strictly increasing")

    @property
    def names(self) -> tuple[str, ...]:
        return (*self.symbols, self.benchmark)

    @property
    def benchmark_index(self) -> int:
        return len(self.symbols)

    @property
    def session_dates(self) -> list[date]:
        return [d.item() for d in self.sessions]


_ARRAYS = ("open_adj", "close_adj", "dollar_volume")


def pack_inputs(inputs: HistoryInputs) -> bytes:
    meta = {
        "symbols": list(inputs.symbols),
        "benchmark": inputs.benchmark,
        "provider": inputs.provider,
        "retrieved_at": inputs.retrieved_at.isoformat(),
    }
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        meta=np.array(json.dumps(meta)),
        sessions=inputs.sessions.astype("datetime64[D]"),
        open_adj=np.asarray(inputs.open_adj, dtype="<f8"),
        close_adj=np.asarray(inputs.close_adj, dtype="<f8"),
        dollar_volume=np.asarray(inputs.dollar_volume, dtype="<f8"),
    )
    return buffer.getvalue()


def unpack_inputs(blob: bytes) -> HistoryInputs:
    with np.load(io.BytesIO(blob), allow_pickle=False) as data:
        meta = json.loads(str(data["meta"]))
        return HistoryInputs(
            symbols=tuple(meta["symbols"]),
            benchmark=meta["benchmark"],
            sessions=data["sessions"],
            provider=meta["provider"],
            retrieved_at=datetime.fromisoformat(meta["retrieved_at"]),
            **{name: data[name] for name in _ARRAYS},
        )


def inputs_hash(inputs: HistoryInputs) -> str:
    """Hash of the data only (names, sessions, prices), not of when it was fetched."""
    digest = hashlib.sha256()
    digest.update(json.dumps([list(inputs.names), inputs.benchmark]).encode())
    digest.update(
        np.ascontiguousarray(inputs.sessions.astype("datetime64[D]")).tobytes()
    )
    for name in _ARRAYS:
        digest.update(
            np.ascontiguousarray(getattr(inputs, name), dtype="<f8").tobytes()
        )
    return digest.hexdigest()
