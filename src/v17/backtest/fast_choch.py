"""Fast vectorized CHoCH (Change of Character) detection for 1m bars.

Replaces smartmoneyconcepts' per-bar scan at O(n*swing) cost with a vectorized
pass. Detects local swing highs/lows via a centered rolling max/min and emits
CHoCH when close breaks the most recent opposite swing — i.e. the first
reversal after a trend.

Semantics preserved vs. smc for our purposes:
- CHoCH BUY = close > last swing high while previous trend was down.
- CHoCH SELL = close < last swing low while previous trend was up.

Not bar-for-bar identical to smc (different swing definition), but produces
comparable candidate set for 1m MSS filtering in `snapshot_at`.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from v17.common.dtos import Swing
from v17.common.types import TF, Side


def _rolling_swing_points(
    highs: np.ndarray, lows: np.ndarray, window: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return boolean masks (is_swing_high, is_swing_low) over the series.

    A bar i is a swing high if its high is >= every high in [i-window, i+window].
    Same symmetric rule for swing lows.
    """
    n = len(highs)
    is_sh = np.zeros(n, dtype=bool)
    is_sl = np.zeros(n, dtype=bool)
    # Rolling max/min (centered) via pandas is fastest here
    h_series = pd.Series(highs)
    l_series = pd.Series(lows)
    rmax = h_series.rolling(window=2 * window + 1, center=True, min_periods=1).max().to_numpy()
    rmin = l_series.rolling(window=2 * window + 1, center=True, min_periods=1).min().to_numpy()
    is_sh = highs >= rmax - 1e-12
    is_sl = lows <= rmin + 1e-12
    # Avoid double-marking first/last window bars (unstable edges)
    is_sh[:window] = False
    is_sh[-window:] = False
    is_sl[:window] = False
    is_sl[-window:] = False
    return is_sh, is_sl


def detect_choch_fast(bars: pd.DataFrame, swing_window: int = 10) -> list[Swing]:
    """Walk bars once, emit CHoCH events using tracked last swing extremes."""
    highs = bars["high"].to_numpy(dtype="float64")
    lows = bars["low"].to_numpy(dtype="float64")
    closes = bars["close"].to_numpy(dtype="float64")
    ts = bars["ts"].tolist()
    is_sh, is_sl = _rolling_swing_points(highs, lows, swing_window)

    out: list[Swing] = []
    last_swing_high: float | None = None
    last_swing_low: float | None = None
    trend: str | None = None  # "up" or "down" after first swing pair

    for i in range(len(bars)):
        confirm_idx = i - swing_window
        if confirm_idx >= 0:
            if is_sh[confirm_idx]:
                last_swing_high = float(highs[confirm_idx])
                if last_swing_low is not None and trend is None:
                    trend = "up" if last_swing_high > last_swing_low else "down"
            if is_sl[confirm_idx]:
                last_swing_low = float(lows[confirm_idx])
                if last_swing_high is not None and trend is None:
                    trend = "down" if last_swing_low < last_swing_high else "up"
        if last_swing_high is None or last_swing_low is None:
            continue
        c = float(closes[i])
        # CHoCH up: previously down trend, close breaks above last swing high
        if trend == "down" and c > last_swing_high:
            out.append(
                Swing(
                    kind="choch",
                    side=Side.BUY,
                    tf=TF.M1,
                    at=ts[i].to_pydatetime(),
                    price=Decimal(str(last_swing_high)),
                )
            )
            trend = "up"
        elif trend == "up" and c < last_swing_low:
            out.append(
                Swing(
                    kind="choch",
                    side=Side.SELL,
                    tf=TF.M1,
                    at=ts[i].to_pydatetime(),
                    price=Decimal(str(last_swing_low)),
                )
            )
            trend = "down"
    return out
