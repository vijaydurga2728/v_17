"""Spec §7, D4-D6, R11: 5-minute three-candle fair value gap completing on/after MSS confirmation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from v17.smc_sb.session import NS_PER_MIN


@dataclass(frozen=True)
class FVG:
    c1_idx: int
    c3_idx: int
    c2_start_ns: int  # displacement candle
    formed_ns: int  # candle-3 close = formation time
    bottom: float
    top: float
    proximal: float  # entry edge: top (long) / bottom (short)
    far: float  # stop edge: bottom (long) / top (short)


def find_fvg(
    c5: pd.DataFrame, side: int, mss_end_ns: int, win_end_ns: int, tf_min: int = 5
) -> FVG | None:
    """First directional FVG whose candle 3 closes in [mss_end_ns, win_end_ns] with three time-contiguous
    candles. Bullish: low3 > high1, zone [high1, low3]. Bearish: high3 < low1, zone [high3, low1]."""
    start, end = c5.start.to_numpy(), c5.end.to_numpy()
    hi, lo = c5.h.to_numpy(), c5.l.to_numpy()
    step = tf_min * NS_PER_MIN
    for k3 in np.flatnonzero((end >= mss_end_ns) & (end <= win_end_ns)):
        k1 = k3 - 2
        if k1 < 0 or start[k3] - start[k1] != 2 * step or start[k3] - start[k3 - 1] != step:
            continue
        if side == 1 and lo[k3] > hi[k1]:
            b, t = float(hi[k1]), float(lo[k3])
            return FVG(int(k1), int(k3), int(start[k3 - 1]), int(end[k3]), b, t, t, b)
        if side == -1 and hi[k3] < lo[k1]:
            b, t = float(hi[k3]), float(lo[k1])
            return FVG(int(k1), int(k3), int(start[k3 - 1]), int(end[k3]), b, t, b, t)
    return None
