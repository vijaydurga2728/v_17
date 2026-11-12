"""Cycle 6 SPX regime: session VWAP + slope + ATR -> trinary state."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _session_vwap(mid: np.ndarray, vol: np.ndarray, session_id: np.ndarray) -> np.ndarray:
    n = len(mid)
    out = np.empty(n, dtype=float)
    cum_pv = 0.0
    cum_v = 0.0
    cur_sid = -1
    for i in range(n):
        if session_id[i] != cur_sid:
            cur_sid = session_id[i]
            cum_pv = 0.0
            cum_v = 0.0
        v = max(float(vol[i]), 1.0)  # guard against zero-volume bars
        cum_pv += mid[i] * v
        cum_v += v
        out[i] = cum_pv / cum_v if cum_v > 0 else mid[i]
    return out


def _atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan, dtype=float)
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    if n < period:
        return out
    atr = tr[1:period+1].mean()
    out[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + tr[i]) / period
        out[i] = atr
    return out


def _rolling_slope(y: np.ndarray, window: int) -> np.ndarray:
    n = len(y)
    out = np.full(n, np.nan, dtype=float)
    if n < window:
        return out
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    for i in range(window - 1, n):
        y_win = y[i - window + 1 : i + 1]
        y_mean = y_win.mean()
        cov = ((x - x_mean) * (y_win - y_mean)).sum()
        out[i] = cov / x_var
    return out


def compute_regime(
    spx_m5: pd.DataFrame,
    k_atr: float,
    slope_window: int,
    session_anchor_hour: int = 8,
    atr_period: int = 14,
) -> pd.DataFrame:
    df = spx_m5.copy()
    ts = pd.to_datetime(df["ts_utc"], unit="ns", utc=True)
    # Session id = calendar date shifted by -session_anchor_hour
    anchored = ts - pd.Timedelta(hours=session_anchor_hour)
    session_id = (anchored.dt.year * 10000 + anchored.dt.month * 100 + anchored.dt.day).to_numpy()

    mid_c = ((df["bid_c"] + df["ask_c"]) * 0.5).to_numpy()
    mid_h = ((df["bid_h"] + df["ask_h"]) * 0.5).to_numpy()
    mid_l = ((df["bid_l"] + df["ask_l"]) * 0.5).to_numpy()
    vol = (df["bid_volume"].fillna(0) + df["ask_volume"].fillna(0)).to_numpy()

    vwap = _session_vwap(mid_c, vol, session_id)
    atr = _atr_wilder(mid_h, mid_l, mid_c, atr_period)
    slope = _rolling_slope(vwap, slope_window)

    # Warmup gate: require both slope and ATR present AND session has >=slope_window bars.
    bars_in_session = np.zeros(len(df), dtype=int)
    cur = -1
    count = 0
    for i, sid in enumerate(session_id):
        if sid != cur:
            cur = sid
            count = 0
        count += 1
        bars_in_session[i] = count

    regime = np.full(len(df), "FLAT", dtype=object)
    have = (~np.isnan(atr)) & (~np.isnan(slope)) & (bars_in_session >= slope_window)
    long_mask = have & (mid_c > vwap + k_atr * atr) & (slope > 0)
    short_mask = have & (mid_c < vwap - k_atr * atr) & (slope < 0)
    regime[long_mask] = "LONG_BIAS"
    regime[short_mask] = "SHORT_BIAS"

    return pd.DataFrame({
        "ts_utc": df["ts_utc"].to_numpy(),
        "mid_close": mid_c,
        "vwap": vwap,
        "atr": atr,
        "slope": slope,
        "regime_state": regime,
    })
