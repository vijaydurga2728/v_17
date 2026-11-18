"""D2 / R5: liquidity sweep on completed 5-minute candles inside the signal window."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Sweep:
    idx: int  # position in the 5 m candle frame
    start_ns: int
    end_ns: int
    ref_name: str  # e.g. "PDL", "ASIA_LOW"
    ref_price: float
    extreme: float  # candle low (long) / high (short)


def find_sweep(
    c5: pd.DataFrame, side: int, refs: dict[str, float], win_start_ns: int, win_end_ns: int
) -> Sweep | None:
    """First 5 m candle in the window trading strictly beyond a reference and closing strictly back inside.

    Long (bullish bias) uses sell-side refs: low < ref and close > ref. Short mirrors with high/close.
    When one candle sweeps several refs, the first in `refs` order is recorded.
    """
    start, end = c5.start.to_numpy(), c5.end.to_numpy()
    lo, hi, cl = c5.l.to_numpy(), c5.h.to_numpy(), c5.c.to_numpy()
    for k in np.flatnonzero((start >= win_start_ns) & (end <= win_end_ns)):
        for name, ref in refs.items():
            if side == 1 and lo[k] < ref and cl[k] > ref:
                return Sweep(int(k), int(start[k]), int(end[k]), name, ref, float(lo[k]))
            if side == -1 and hi[k] > ref and cl[k] < ref:
                return Sweep(int(k), int(start[k]), int(end[k]), name, ref, float(hi[k]))
    return None
