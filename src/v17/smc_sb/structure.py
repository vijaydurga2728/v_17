"""Strict pivots (D1, D3) and the 15-minute market structure shift (D3, R9, R10)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def pivot_flags(
    high: np.ndarray, low: np.ndarray, left: int, right: int
) -> tuple[np.ndarray, np.ndarray]:
    """Strict pivots: high[k] > every high in [k-left, k+right] except itself (mirror for lows).

    Equal neighbours => not a pivot. Positions without `left` / `right` neighbours are never pivots.
    The flag at k uses bars up to k+right; callers must only use it once bar k+right is complete.
    """
    n = len(high)
    ph = np.zeros(n, dtype=bool)
    pl = np.zeros(n, dtype=bool)
    for k in range(left, n - right):
        nb = np.r_[np.arange(k - left, k), np.arange(k + 1, k + right + 1)]
        ph[k] = bool(np.all(high[k] > high[nb]))
        pl[k] = bool(np.all(low[k] < low[nb]))
    return ph, pl


@dataclass(frozen=True)
class MSS:
    idx: int  # position in the 15 m candle frame
    start_ns: int
    end_ns: int  # confirmation time (candle close)
    close: float
    swing_idx: int  # 15 m candle position of the broken swing
    swing_price: float


def latest_confirmed(flags: np.ndarray, before: int, right: int) -> int:
    """Latest pivot position k with k + right <= before - 1 (its right-side candles completed), or -1."""
    upto = before - 1 - right
    if upto < 0:
        return -1
    hits = np.flatnonzero(flags[: upto + 1])
    return int(hits[-1]) if len(hits) else -1


def find_mss(
    c15: pd.DataFrame,
    ph: np.ndarray,
    pl: np.ndarray,
    side: int,
    after_ns: int,
    win_start_ns: int,
    win_end_ns: int,
    right: int,
) -> tuple[MSS | None, str]:
    """R9: first completed 15 m candle in the window closing after `after_ns` and strictly beyond the latest
    confirmed opposing swing (swing high for longs, swing low for shorts). Exactly one MSS: the first."""
    start, end, close = c15.start.to_numpy(), c15.end.to_numpy(), c15.c.to_numpy()
    cand = np.flatnonzero((start >= win_start_ns) & (end <= win_end_ns) & (end > after_ns))
    if len(cand) == 0:
        return None, "no_15m_candle_after_sweep"
    flags, price = (ph, c15.h.to_numpy()) if side == 1 else (pl, c15.l.to_numpy())
    for pos, m in enumerate(cand):
        k = latest_confirmed(flags, int(m), right)
        if k < 0:
            if pos == 0:
                return None, "no_confirmed_swing"
            continue
        if (side == 1 and close[m] > price[k]) or (side == -1 and close[m] < price[k]):
            return MSS(
                int(m), int(start[m]), int(end[m]), float(close[m]), k, float(price[k])
            ), "ok"
    return None, "no_mss"
