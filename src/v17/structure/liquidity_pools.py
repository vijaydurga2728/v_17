"""SB-02 liquidity pool enumeration (no Asian fallback, no PDH/PDL).

Audit 1 classification: RESEARCH_HYPOTHESIS. Pools eligible for SB-02:
  - session_high / session_low: extreme in [00:00 NY, window_start_ns).
    Caller is responsible for providing bars that cover from NY midnight.
  - prev_hour_high / prev_hour_low: extreme in [window_start - 1h, window_start).
  - Prominent M15 swing in last 45 min: INTENTIONALLY OMITTED here;
    the swing-based pool is layered by Task 5.3 (engine runner wiring)
    if needed by trade-count calibration.
"""
from __future__ import annotations

import pandas as pd

_ONE_HOUR_NS = 3_600_000_000_000


def enumerate_pools(bars: pd.DataFrame, window_start_ns: int, now_ns: int) -> list[dict]:
    pools: list[dict] = []
    df = bars[bars["ts_utc"] < now_ns]
    if df.empty:
        return pools

    pre_window = df[df["ts_utc"] < window_start_ns]
    if not pre_window.empty:
        hi_idx = pre_window["bid_h"].idxmax()
        lo_idx = pre_window["bid_l"].idxmin()
        pools.append({
            "kind": "session_high",
            "price": float(pre_window.loc[hi_idx, "bid_h"]),
            "ts_utc": int(pre_window.loc[hi_idx, "ts_utc"]),
        })
        pools.append({
            "kind": "session_low",
            "price": float(pre_window.loc[lo_idx, "bid_l"]),
            "ts_utc": int(pre_window.loc[lo_idx, "ts_utc"]),
        })

    prev_hr = df[
        (df["ts_utc"] >= window_start_ns - _ONE_HOUR_NS)
        & (df["ts_utc"] < window_start_ns)
    ]
    if not prev_hr.empty:
        hi_idx = prev_hr["bid_h"].idxmax()
        lo_idx = prev_hr["bid_l"].idxmin()
        pools.append({
            "kind": "prev_hour_high",
            "price": float(prev_hr.loc[hi_idx, "bid_h"]),
            "ts_utc": int(prev_hr.loc[hi_idx, "ts_utc"]),
        })
        pools.append({
            "kind": "prev_hour_low",
            "price": float(prev_hr.loc[lo_idx, "bid_l"]),
            "ts_utc": int(prev_hr.loc[lo_idx, "ts_utc"]),
        })

    return pools
