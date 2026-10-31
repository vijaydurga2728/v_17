from __future__ import annotations

import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].to_numpy(dtype="float64")
    low = df["low"].to_numpy(dtype="float64")
    close = df["close"].to_numpy(dtype="float64")
    prev_close = np.concatenate(([np.nan], close[:-1]))
    tr = np.maximum(
        high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close))
    )
    out = np.full(len(df), np.nan)
    if len(df) < period:
        return pd.Series(out, index=df.index, name="atr")
    first = np.nanmean(tr[:period])
    out[period - 1] = first
    for i in range(period, len(df)):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return pd.Series(out, index=df.index, name="atr")
