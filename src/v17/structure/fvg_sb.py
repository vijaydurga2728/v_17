"""Causal FVG detector for the SB engine pipeline.

Separate from v17.structure.fvg (legacy, Decimal + Zone-based). This module
operates on paired-bars DataFrames (bid_h, bid_l, ts_utc int64) and returns
plain dict records. Strict causality: only bars at index i where i+2 fully
precedes as_of_ns are considered.
"""
from __future__ import annotations

import pandas as pd


def detect_fvgs_at(bars: pd.DataFrame, as_of_ns: int) -> list[dict]:
    df = bars[bars["ts_utc"] < as_of_ns].reset_index(drop=True)
    out: list[dict] = []
    n = len(df)
    if n < 3:
        return out
    highs = df["bid_h"].to_numpy()
    lows = df["bid_l"].to_numpy()
    ts = df["ts_utc"].to_numpy()
    for i in range(2, n):
        # Bullish: L_i > H_{i-2}
        if lows[i] > highs[i - 2]:
            bottom = float(highs[i - 2])
            top = float(lows[i])
            out.append({
                "kind": "bullish",
                "ts_ns": int(ts[i]),
                "top": top,
                "bottom": bottom,
                "ce": (top + bottom) / 2.0,
            })
        # Bearish: H_i < L_{i-2}
        elif highs[i] < lows[i - 2]:
            bottom = float(highs[i])
            top = float(lows[i - 2])
            out.append({
                "kind": "bearish",
                "ts_ns": int(ts[i]),
                "top": top,
                "bottom": bottom,
                "ce": (top + bottom) / 2.0,
            })
    return out
