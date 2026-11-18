"""D1 higher-timeframe bias from strict 2/2 daily pivots, and R8 daily swing range."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from v17.smc_sb.structure import pivot_flags


@dataclass(frozen=True)
class Bias:
    direction: int  # +1 bullish, -1 bearish, 0 neutral
    reason: str
    last_high: float = float("nan")
    prev_high: float = float("nan")
    last_low: float = float("nan")
    prev_low: float = float("nan")


class DailyStructure:
    """Pivots over the whole daily table; queries only use pivots confirmed before the trading date."""

    def __init__(self, daily: pd.DataFrame, left: int, right: int) -> None:
        self.dates = daily.index
        self.h, self.l = daily.h.to_numpy(float), daily.l.to_numpy(float)
        self.right = right
        self.ph, self.pl = pivot_flags(self.h, self.l, left, right)

    def bias(self, i: int) -> Bias:
        """Bias for the trading date at daily position i (rows < i only; pivot k usable if k+right <= i-1)."""
        upto = i - 1 - self.right
        if upto < 0:
            return Bias(0, "insufficient_structure")
        hs = np.flatnonzero(self.ph[: upto + 1])
        ls = np.flatnonzero(self.pl[: upto + 1])
        if len(hs) < 2 or len(ls) < 2:
            return Bias(0, "insufficient_structure")
        lh, ph_, ll, pl_ = self.h[hs[-1]], self.h[hs[-2]], self.l[ls[-1]], self.l[ls[-2]]
        if lh > ph_ and ll > pl_:
            return Bias(1, "HH+HL", lh, ph_, ll, pl_)
        if lh < ph_ and ll < pl_:
            return Bias(-1, "LH+LL", lh, ph_, ll, pl_)
        return Bias(0, "mixed_or_equal", lh, ph_, ll, pl_)
