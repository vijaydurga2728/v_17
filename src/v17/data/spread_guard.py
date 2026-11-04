"""SpreadGuard — Policy C (active this cycle per spec §12 amendment 2026-11-03).

Reject an entry when current measured spread exceeds SPREAD_GUARD_MULT ×
the rolling trailing-30-day median for the same (symbol, minute-of-day).
"""
from __future__ import annotations

import pandas as pd

from v17.setups.sb_constants import SPREAD_GUARD_LOOKBACK_DAYS, SPREAD_GUARD_MULT


_ONE_DAY_NS = 86_400_000_000_000


class SpreadGuard:
    def __init__(self, bars: pd.DataFrame, symbol: str):
        df = bars[bars["symbol"] == symbol].copy()
        if df.empty:
            self._df = df
            self._symbol = symbol
            return
        ts = pd.to_datetime(df["ts_utc"], utc=True)
        df["_mod"] = ts.dt.hour * 60 + ts.dt.minute
        self._df = df[["ts_utc", "_mod", "spread_mid"]].reset_index(drop=True)
        self._symbol = symbol

    def should_reject(self, ts_utc_ns: int, current_spread: float) -> bool:
        if self._df.empty:
            return False
        ref = pd.Timestamp(ts_utc_ns, tz="UTC")
        mod = ref.hour * 60 + ref.minute
        window_start = ts_utc_ns - SPREAD_GUARD_LOOKBACK_DAYS * _ONE_DAY_NS
        sub = self._df[
            (self._df["_mod"] == mod)
            & (self._df["ts_utc"] >= window_start)
            & (self._df["ts_utc"] < ts_utc_ns)
        ]
        if sub.empty:
            return False
        median = float(sub["spread_mid"].median())
        return current_spread > SPREAD_GUARD_MULT * median
