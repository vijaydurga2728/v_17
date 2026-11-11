"""Statistics bundle for MCPT and secondary gates (spec section 7.2)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class StatsBundle:
    sharpe: float
    pf: float
    max_dd: float
    r2: float
    trade_count: int
    win_rate: float
    avg_r: float


def compute_stats(pnls: np.ndarray, timestamps_ns: np.ndarray) -> StatsBundle:
    pnls = np.asarray(pnls, dtype=float)
    n = int(len(pnls))
    if n == 0:
        return StatsBundle(sharpe=0.0, pf=0.0, max_dd=0.0, r2=0.0,
                           trade_count=0, win_rate=0.0, avg_r=0.0)
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = float(dd.max())
    wins = float(pnls[pnls > 0].sum())
    losses = float(-pnls[pnls < 0].sum())
    if losses > 0:
        pf = wins / losses
    else:
        pf = float("inf") if wins > 0 else 0.0
    win_rate = float((pnls > 0).mean())
    avg_r = float(pnls.mean())
    std = float(pnls.std(ddof=1)) if n > 1 else 0.0
    sharpe = float((pnls.mean() / std) * np.sqrt(252)) if std > 0 else 0.0
    if n > 1:
        x = np.arange(n, dtype=float)
        slope, intercept = np.polyfit(x, equity, 1)
        fitted = slope * x + intercept
        ss_res = float(((equity - fitted) ** 2).sum())
        ss_tot = float(((equity - equity.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    else:
        r2 = 0.0
    return StatsBundle(
        sharpe=sharpe, pf=pf, max_dd=max_dd, r2=r2,
        trade_count=n, win_rate=win_rate, avg_r=avg_r,
    )
