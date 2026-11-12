"""Cycle 6 FX micro-trigger: session VWAP pullback + confirm bar."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.setups.c6_regime import _atr_wilder, _session_vwap


def compute_micro_signals(
    fx_m5: pd.DataFrame,
    confirm_body_mult: float,
    atr_period: int = 14,
    session_anchor_hour: int = 8,
    pullback_lookback: int = 3,
) -> pd.DataFrame:
    df = fx_m5.copy()
    ts = pd.to_datetime(df["ts_utc"], unit="ns", utc=True)
    anchored = ts - pd.Timedelta(hours=session_anchor_hour)
    session_id = (anchored.dt.year * 10000 + anchored.dt.month * 100 + anchored.dt.day).to_numpy()

    mid_o = ((df["bid_o"] + df["ask_o"]) * 0.5).to_numpy()
    mid_c = ((df["bid_c"] + df["ask_c"]) * 0.5).to_numpy()
    mid_h = ((df["bid_h"] + df["ask_h"]) * 0.5).to_numpy()
    mid_l = ((df["bid_l"] + df["ask_l"]) * 0.5).to_numpy()
    vol = (df["bid_volume"].fillna(0) + df["ask_volume"].fillna(0)).to_numpy()

    vwap = _session_vwap(mid_c, vol, session_id)
    atr = _atr_wilder(mid_h, mid_l, mid_c, atr_period)

    n = len(df)
    pullback = np.zeros(n, dtype=bool)
    for i in range(n):
        start = max(0, i - pullback_lookback + 1)
        # Any bar in window where VWAP within [low, high].
        v_win = vwap[start:i+1]
        h_win = mid_h[start:i+1]
        l_win = mid_l[start:i+1]
        pullback[i] = bool(((l_win <= v_win) & (v_win <= h_win)).any())

    body = mid_c - mid_o
    atr_safe = np.where(np.isnan(atr), np.inf, atr)
    body_ok_long = body >= confirm_body_mult * atr_safe
    body_ok_short = (-body) >= confirm_body_mult * atr_safe

    have_atr = ~np.isnan(atr)
    confirm_long = pullback & have_atr & (mid_c > vwap) & (mid_c > mid_o) & body_ok_long
    confirm_short = pullback & have_atr & (mid_c < vwap) & (mid_c < mid_o) & body_ok_short

    return pd.DataFrame({
        "ts_utc": df["ts_utc"].to_numpy(),
        "fx_mid_close": mid_c,
        "fx_vwap": vwap,
        "fx_atr": atr,
        "pullback": pullback,
        "confirm_long": confirm_long,
        "confirm_short": confirm_short,
    })
