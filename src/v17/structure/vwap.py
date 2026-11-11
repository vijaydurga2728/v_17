"""Session VWAP computation.

Cumulative volume-weighted average price over a bounded session window.
If `volume` column is absent (CFD tick-data case), falls back to the
cumulative mean of typical_price.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_session_vwap(
    bars: pd.DataFrame, session_start_ns: int, session_end_ns: int
) -> pd.Series:
    """Return cumulative session VWAP indexed identically to `bars`.

    typical_price = (high + low + close) / 3
    VWAP_i = cumsum(tp * vol)[i] / cumsum(vol)[i]  within the session
    NaN outside [session_start_ns, session_end_ns].
    """
    ts = bars["ts_ns"].to_numpy()
    mask = (ts >= session_start_ns) & (ts <= session_end_ns)
    out = pd.Series(np.nan, index=bars.index, dtype=float)

    if not mask.any():
        return out

    tp = (bars["high"].to_numpy() + bars["low"].to_numpy() + bars["close"].to_numpy()) / 3.0

    if "volume" in bars.columns:
        vol = bars["volume"].to_numpy(dtype=float)
    else:
        vol = np.ones_like(tp)

    tp_sess = tp[mask]
    vol_sess = vol[mask]

    cum_tp_vol = np.cumsum(tp_sess * vol_sess)
    cum_vol = np.cumsum(vol_sess)
    # Guard against zero-volume bars by replacing with 1 (equivalent to typical-price fallback).
    cum_vol = np.where(cum_vol == 0, 1.0, cum_vol)

    vwap_sess = cum_tp_vol / cum_vol
    out.iloc[np.where(mask)[0]] = vwap_sess
    return out
