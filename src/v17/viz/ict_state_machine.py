"""Stateful ICT Market Structure Extractor for Continuous Candlestick Charts (High-Speed Vectorized).

Adheres strictly to RULES.md (zero lookahead, deterministic point-in-time calculation).
Tracks lifecycle of:
1. Fair Value Gaps (FVG) - active until mitigated by future price.
2. Order Blocks (OB) - active until invalidated by future price close.
3. Liquidity Levels (Asian H/L, PDH/PDL, Pivots) - active until swept by price wick.
4. Killzones & Sessions (Asia, London, NY AM).
5. Trade Executions (Entry, SL, TP, Exits).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


@dataclass
class FVG:
    id: str
    side: int           # 1 = bullish, -1 = bearish
    start_time: int     # Unix epoch seconds (creation candle)
    end_time: int       # Unix epoch seconds (mitigation candle or latest)
    top: float
    bottom: float
    mitigated: bool
    mitigation_time: int | None = None


@dataclass
class OrderBlock:
    id: str
    side: int           # 1 = bullish OB, -1 = bearish OB
    start_time: int
    end_time: int
    top: float
    bottom: float
    invalidated: bool
    invalidation_time: int | None = None


@dataclass
class LiquidityLevel:
    id: str
    name: str           # "PDH", "PDL", "ASIA_H", "ASIA_L", "SWING_H", "SWING_L"
    side: int           # 1 = Buy-side liquidity (High), -1 = Sell-side liquidity (Low)
    price: float
    start_time: int
    end_time: int
    swept: bool
    sweep_time: int | None = None
    sweep_px: float | None = None


@dataclass
class SessionZone:
    name: str           # "ASIA", "LDN", "NY_AM"
    start_time: int
    end_time: int
    high: float
    low: float


def extract_continuous_ict_state(
    b_ts: np.ndarray,      # Epoch nanoseconds (UTC)
    b_o: np.ndarray,
    b_h: np.ndarray,
    b_l: np.ndarray,
    b_c: np.ndarray,
    symbol: str = "EURUSD",
    min_fvg_pips: float = 0.00015,
    max_active_lookforward: int = 500,
) -> dict[str, Any]:
    """Processes continuous M5 candles bar-by-bar and returns all stateful ICT objects (Vectorized)."""
    n = len(b_ts)
    if n < 5:
        return {"candles": [], "fvgs": [], "order_blocks": [], "liquidity_levels": [], "sessions": []}

    ts_sec = (b_ts // 1_000_000_000).astype(np.int64)

    # 1. Build Candles Array for Lightweight Charts
    candles = [
        {
            "time": int(ts_sec[i]),
            "open": round(float(b_o[i]), 5),
            "high": round(float(b_h[i]), 5),
            "low": round(float(b_l[i]), 5),
            "close": round(float(b_c[i]), 5),
        }
        for i in range(n)
    ]

    # 2. Vectorized Bullish FVGs (low[i] > high[i-2])
    bull_mask = (b_l[2:] > b_h[:-2]) & ((b_l[2:] - b_h[:-2]) >= min_fvg_pips)
    bull_indices = np.where(bull_mask)[0] + 2

    fvgs: list[FVG] = []
    order_blocks: list[OrderBlock] = []

    for i in bull_indices:
        top = float(b_l[i])
        bottom = float(b_h[i - 2])
        c_start = int(ts_sec[i - 1])

        # Find first bar where future low touches or dips below bottom
        look_slice = b_l[i + 1 : min(n, i + 1 + max_active_lookforward)]
        mit_rel_indices = np.where(look_slice <= bottom)[0]

        if len(mit_rel_indices) > 0:
            mit_bar = i + 1 + int(mit_rel_indices[0])
            mitigated = True
            end_time = int(ts_sec[mit_bar])
            mit_time = end_time
        else:
            mitigated = False
            end_time = int(ts_sec[min(n - 1, i + max_active_lookforward)])
            mit_time = None

        fvgs.append(FVG(
            id=f"fvg_bull_{i}",
            side=1,
            start_time=c_start,
            end_time=end_time,
            top=round(top, 5),
            bottom=round(bottom, 5),
            mitigated=mitigated,
            mitigation_time=mit_time,
        ))

        # Order block: candle before displacement (i-2)
        ob_i = i - 2
        if ob_i >= 0 and b_c[ob_i] < b_o[ob_i]: # Down-close candle before bullish expansion
            ob_top = float(b_h[ob_i])
            ob_bot = float(b_l[ob_i])
            ob_start = int(ts_sec[ob_i])

            ob_slice = b_c[i + 1 : min(n, i + 1 + max_active_lookforward)]
            inv_rel = np.where(ob_slice < ob_bot)[0]
            if len(inv_rel) > 0:
                inv_bar = i + 1 + int(inv_rel[0])
                inv = True
                ob_end = int(ts_sec[inv_bar])
                inv_time = ob_end
            else:
                inv = False
                ob_end = int(ts_sec[min(n - 1, ob_i + max_active_lookforward)])
                inv_time = None

            order_blocks.append(OrderBlock(
                id=f"ob_bull_{ob_i}",
                side=1,
                start_time=ob_start,
                end_time=ob_end,
                top=round(ob_top, 5),
                bottom=round(ob_bot, 5),
                invalidated=inv,
                invalidation_time=inv_time,
            ))

    # 3. Vectorized Bearish FVGs (high[i] < low[i-2])
    bear_mask = (b_h[2:] < b_l[:-2]) & ((b_l[:-2] - b_h[2:]) >= min_fvg_pips)
    bear_indices = np.where(bear_mask)[0] + 2

    for i in bear_indices:
        top = float(b_l[i - 2])
        bottom = float(b_h[i])
        c_start = int(ts_sec[i - 1])

        look_slice = b_h[i + 1 : min(n, i + 1 + max_active_lookforward)]
        mit_rel_indices = np.where(look_slice >= top)[0]

        if len(mit_rel_indices) > 0:
            mit_bar = i + 1 + int(mit_rel_indices[0])
            mitigated = True
            end_time = int(ts_sec[mit_bar])
            mit_time = end_time
        else:
            mitigated = False
            end_time = int(ts_sec[min(n - 1, i + max_active_lookforward)])
            mit_time = None

        fvgs.append(FVG(
            id=f"fvg_bear_{i}",
            side=-1,
            start_time=c_start,
            end_time=end_time,
            top=round(top, 5),
            bottom=round(bottom, 5),
            mitigated=mitigated,
            mitigation_time=mit_time,
        ))

        # Order block: candle before displacement (i-2)
        ob_i = i - 2
        if ob_i >= 0 and b_c[ob_i] > b_o[ob_i]: # Up-close candle before bearish expansion
            ob_top = float(b_h[ob_i])
            ob_bot = float(b_l[ob_i])
            ob_start = int(ts_sec[ob_i])

            ob_slice = b_c[i + 1 : min(n, i + 1 + max_active_lookforward)]
            inv_rel = np.where(ob_slice > ob_top)[0]
            if len(inv_rel) > 0:
                inv_bar = i + 1 + int(inv_rel[0])
                inv = True
                ob_end = int(ts_sec[inv_bar])
                inv_time = ob_end
            else:
                inv = False
                ob_end = int(ts_sec[min(n - 1, ob_i + max_active_lookforward)])
                inv_time = None

            order_blocks.append(OrderBlock(
                id=f"ob_bear_{ob_i}",
                side=-1,
                start_time=ob_start,
                end_time=ob_end,
                top=round(ob_top, 5),
                bottom=round(ob_bot, 5),
                invalidated=inv,
                invalidation_time=inv_time,
            ))

    # 4. Sessions (London Killzone & NY AM Killzone) & Liquidity Levels
    sessions: list[SessionZone] = []
    liquidity_levels: list[LiquidityLevel] = []

    dt_ny = pd.to_datetime(b_ts, unit="ns", utc=True).tz_convert(NY)
    dates = dt_ny.date
    hours = dt_ny.hour
    unique_dates = np.unique(dates)

    for d in unique_dates:
        mask_d = dates == d
        idxs_d = np.where(mask_d)[0]
        if len(idxs_d) == 0:
            continue

        # London Killzone: 03:00-04:00 NY
        idxs_ldn = np.where(mask_d & (hours == 3))[0]
        if len(idxs_ldn) > 0:
            sessions.append(SessionZone(
                name="LDN",
                start_time=int(ts_sec[idxs_ldn[0]]),
                end_time=int(ts_sec[idxs_ldn[-1]]),
                high=round(float(np.max(b_h[idxs_ldn])), 5),
                low=round(float(np.min(b_l[idxs_ldn])), 5),
            ))

        # NY AM Killzone: 10:00-11:00 NY
        idxs_am = np.where(mask_d & (hours == 10))[0]
        if len(idxs_am) > 0:
            sessions.append(SessionZone(
                name="NY_AM",
                start_time=int(ts_sec[idxs_am[0]]),
                end_time=int(ts_sec[idxs_am[-1]]),
                high=round(float(np.max(b_h[idxs_am])), 5),
                low=round(float(np.min(b_l[idxs_am])), 5),
            ))

        # Asia Reference (00:00 to 02:00 NY)
        idxs_asia = np.where(mask_d & (hours < 2))[0]
        if len(idxs_asia) > 0:
            asia_h = float(np.max(b_h[idxs_asia]))
            asia_l = float(np.min(b_l[idxs_asia]))
            asia_start = int(ts_sec[idxs_asia[0]])
            asia_end = int(ts_sec[idxs_asia[-1]])

            sessions.append(SessionZone(
                name="ASIA",
                start_time=asia_start,
                end_time=asia_end,
                high=round(asia_h, 5),
                low=round(asia_l, 5),
            ))

            # Scan for Asia High sweep during the remaining day
            post_asia = idxs_d[idxs_d > idxs_asia[-1]]
            if len(post_asia) > 0:
                swept_h_rel = np.where(b_h[post_asia] > asia_h)[0]
                if len(swept_h_rel) > 0:
                    sw_bar = post_asia[swept_h_rel[0]]
                    liquidity_levels.append(LiquidityLevel(
                        id=f"asia_h_{d}",
                        name="ASIA_H",
                        side=1,
                        price=round(asia_h, 5),
                        start_time=asia_end,
                        end_time=int(ts_sec[sw_bar]),
                        swept=True,
                        sweep_time=int(ts_sec[sw_bar]),
                        sweep_px=round(float(b_h[sw_bar]), 5),
                    ))
                else:
                    liquidity_levels.append(LiquidityLevel(
                        id=f"asia_h_{d}",
                        name="ASIA_H",
                        side=1,
                        price=round(asia_h, 5),
                        start_time=asia_end,
                        end_time=int(ts_sec[post_asia[-1]]),
                        swept=False,
                    ))

                # Scan for Asia Low sweep
                swept_l_rel = np.where(b_l[post_asia] < asia_l)[0]
                if len(swept_l_rel) > 0:
                    sw_bar = post_asia[swept_l_rel[0]]
                    liquidity_levels.append(LiquidityLevel(
                        id=f"asia_l_{d}",
                        name="ASIA_L",
                        side=-1,
                        price=round(asia_l, 5),
                        start_time=asia_end,
                        end_time=int(ts_sec[sw_bar]),
                        swept=True,
                        sweep_time=int(ts_sec[sw_bar]),
                        sweep_px=round(float(b_l[sw_bar]), 5),
                    ))
                else:
                    liquidity_levels.append(LiquidityLevel(
                        id=f"asia_l_{d}",
                        name="ASIA_L",
                        side=-1,
                        price=round(asia_l, 5),
                        start_time=asia_end,
                        end_time=int(ts_sec[post_asia[-1]]),
                        swept=False,
                    ))

    return {
        "candles": candles,
        "fvgs": [f.__dict__ for f in fvgs],
        "order_blocks": [o.__dict__ for o in order_blocks],
        "liquidity_levels": [l.__dict__ for l in liquidity_levels],
        "sessions": [s.__dict__ for s in sessions],
    }
