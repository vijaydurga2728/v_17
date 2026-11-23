"""Cycle 24: Silver Bullet Antigravity — Advanced Institutional ICT Engine.

Modeled after Michael J. Huddleston's core institutional teachings and 20+ years ICT experience:
1. Higher Timeframe Draw on Liquidity (DOL):
   - External Range Liquidity (ERL) vs Internal Range Liquidity (IRL).
   - Explicit sweep of Asian High/Low or Previous Day High/Low (PDH/PDL) determines DOL.
2. Dealing Range & Equilibrium (Premium vs Discount):
   - Strict rule: NEVER buy in Premium (>50%); NEVER sell in Discount (<50%).
3. Algorithmic Silver Bullet Windows:
   - London Silver Bullet: 03:00–04:00 AM NY (1:30–2:30 PM IST).
   - New York AM Opening Drive: 10:00–11:00 AM NY (8:30–9:30 PM IST).
   - New York PM Session: 02:00–03:00 PM NY (12:30–1:30 AM IST).
4. Energetic Displacement & Market Structure Shift (MSS):
   - Displacement candle with >= 65% body ratio and range >= 1.25x ATR breaking swing pivot.
5. Consequent Encroachment (CE) & Proximal Edge Execution:
   - Limit entry placed at FVG proximal edge (or CE 50%).
   - Stop loss placed strictly at the structural manipulation anchor extreme (never tight retail stops).
   - Target: 2.0R to 3.0R directed at the unmitigated opposing liquidity pool.
6. Strict Zero-Lookahead & Full Cost Realism under RULES.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Spec:
    min_stop: float      # Minimum stop distance
    max_stop: float      # Maximum stop distance
    slip: float          # Per-side slippage in price units
    commission_rt: float # Round-trip commission in price units per unit traded


SPECS: Final[dict[str, Spec]] = {
    "EURUSD": Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006),
    "GBPUSD": Spec(min_stop=0.0015, max_stop=0.0035, slip=0.00005, commission_rt=0.00006),
    "USATECHIDXUSD": Spec(min_stop=8.0, max_stop=50.0, slip=0.5, commission_rt=0.0),
    "XAUUSD": Spec(min_stop=2.50, max_stop=10.00, slip=0.15, commission_rt=0.0),
    "USA500IDXUSD": Spec(min_stop=1.5, max_stop=15.0, slip=0.5, commission_rt=0.0),
}

# The 3 Michael Huddleston Silver Bullet Algorithmic Windows
WINDOWS: Final[dict[str, tuple[tuple[int, int], tuple[int, int]]]] = {
    "LDN": ((3, 0), (4, 0)),    # 03:00 - 04:00 AM NY (London Open)
    "AM":  ((10, 0), (11, 0)),  # 10:00 - 11:00 AM NY (New York AM)
    "PM":  ((14, 0), (15, 0)),  # 14:00 - 15:00 NY (New York PM)
}

SESSION_ENDS: Final[dict[str, tuple[int, int]]] = {
    "LDN": (8, 0),    # London trade management until 08:00 NY
    "AM":  (16, 30),  # NY AM trade management until 16:30 NY auto-flatten
    "PM":  (16, 30),  # NY PM auto-flatten
}

BODY_RATIO_MIN: Final[float] = 0.65
RANGE_ATR_MULT: Final[float] = 1.25
TARGET_RR: Final[float] = 2.0
ADR_MAX_PCT: Final[float] = 0.80


@dataclass
class DayContext:
    pdh: float
    pdl: float
    adr10: float
    asia_h: float
    asia_l: float
    dol_side: int        # 1 = Bullish DOL (targets BSL), -1 = Bearish DOL (targets SSL), 0 = Neutral
    equilibrium: float   # 50% dealing range midpoint
    adr_exhausted: bool


def compute_institutional_context(
    b_ts: np.ndarray,
    b_mid_h: np.ndarray,
    b_mid_l: np.ndarray,
    b_mid_c: np.ndarray,
    day_date: str,
    daily_summary: pd.DataFrame,
    window: str,
) -> DayContext | None:
    """Computes HTF Draw on Liquidity (DOL), Asian Range, and Dealing Range Equilibrium."""
    try:
        row = daily_summary.loc[day_date]
        pdh = float(row["pdh"])
        pdl = float(row["pdl"])
        adr10 = float(row["adr10"])
    except (KeyError, TypeError):
        return None

    if not (np.isfinite(pdh) and np.isfinite(pdl) and np.isfinite(adr10)):
        return None

    (sh, sm), _ = WINDOWS[window]
    day_start_ns = pd.Timestamp(day_date).tz_localize(NY).tz_convert("UTC").value
    ws_ns = day_start_ns + (sh * 3600 + sm * 60) * 1_000_000_000

    i_start = np.searchsorted(b_ts, day_start_ns)
    i_ws = np.searchsorted(b_ts, ws_ns)
    if i_ws <= i_start + 5:
        return None

    intra_h = float(np.max(b_mid_h[i_start:i_ws]))
    intra_l = float(np.min(b_mid_l[i_start:i_ws]))
    intra_range = intra_h - intra_l

    # ADR Exhaustion
    adr_exhausted = intra_range >= ADR_MAX_PCT * adr10

    # Asian Range (00:00 to 02:00 NY for London; 00:00 to 09:30 NY for AM)
    asia_end_h, asia_end_m = (2, 0) if window == "LDN" else ((9, 30) if window == "AM" else (13, 30))
    asia_end_ns = day_start_ns + (asia_end_h * 3600 + asia_end_m * 60) * 1_000_000_000
    i_asia_end = np.searchsorted(b_ts, asia_end_ns)

    if i_asia_end > i_start:
        asia_h = float(np.max(b_mid_h[i_start:i_asia_end]))
        asia_l = float(np.min(b_mid_l[i_start:i_asia_end]))
    else:
        asia_h, asia_l = intra_h, intra_l

    # Pre-market Dealing Range & Equilibrium
    equilibrium = (max(intra_h, pdh) + min(intra_l, pdl)) / 2.0

    # Determine Institutional Draw on Liquidity (DOL):
    # Did prior price action sweep Sell-Side Liquidity (SSL: Asia Low or PDL)?
    pdl_swept = intra_l < pdl or intra_l < asia_l
    # Did prior price action sweep Buy-Side Liquidity (BSL: Asia High or PDH)?
    pdh_swept = intra_h > pdh or intra_h > asia_h

    cur_px = float(b_mid_c[i_ws - 1])

    if pdl_swept and not pdh_swept:
        # Swept SSL: High-probability expansion toward Buy-Side Liquidity (BSL)
        dol_side = 1
    elif pdh_swept and not pdl_swept:
        # Swept BSL: High-probability expansion toward Sell-Side Liquidity (SSL)
        dol_side = -1
    else:
        # Check Discount vs Premium relative to dealing range
        if cur_px < equilibrium:
            dol_side = 1  # In Discount: Seek BSL
        elif cur_px > equilibrium:
            dol_side = -1 # In Premium: Seek SSL
        else:
            dol_side = 0

    return DayContext(pdh, pdl, adr10, asia_h, asia_l, dol_side, equilibrium, adr_exhausted)


@dataclass(frozen=True)
class Setup:
    side: int
    sweep_m5: int
    anchor_px: float     # Structural manipulation extreme
    c3_m5: int          # M5 candle confirming MSS + FVG
    c3_close_m1: int    # M1 index when candle 3 closes (order placement timestamp)
    entry_px: float     # Proximal edge of FVG
    ce_px: float        # Consequent Encroachment (50% midpoint of FVG)
    sl_px: float        # Stop loss anchored beyond structural extreme
    tp_px: float        # Target
    risk_dist: float
    rr: float


def find_setup(
    m5_ts_start: np.ndarray,
    m5_o: np.ndarray, m5_h: np.ndarray, m5_l: np.ndarray, m5_c: np.ndarray,
    m5_atr: np.ndarray, m5_m1_end: np.ndarray,
    ph5: np.ndarray, pl5: np.ndarray,
    m5_start_idx: int,
    m5_end_idx: int,
    ctx: DayContext,
    sp: Spec,
    current_spread: float,
) -> Setup | None:
    """Detects an advanced Michael Huddleston Silver Bullet setup on M5.
    
    Enforces:
    1. Strict DOL Alignment (seeking opposing liquidity pool).
    2. Dealing Range Equilibrium: Longs strictly in Discount; Shorts strictly in Premium.
    3. Structural Sweep Manipulation Anchor.
    4. Institutional Displacement: Candle 2 body >= 65% and range >= 1.25x ATR.
    5. Clean Market Structure Shift (MSS) past swing pivot.
    """
    if ctx.adr_exhausted or ctx.dol_side == 0:
        return None

    # Step through candidate M5 FVG displacement candles (Candle 2)
    for c2 in range(m5_start_idx + 1, m5_end_idx):
        c1 = c2 - 1
        c3 = c2 + 1
        if c3 > m5_end_idx:
            break

        c2_body = abs(m5_c[c2] - m5_o[c2])
        c2_range = m5_h[c2] - m5_l[c2]
        if c2_range <= 0:
            continue
        body_ratio = c2_body / c2_range

        # Displacement criteria
        if body_ratio < BODY_RATIO_MIN:
            continue
        if m5_atr[c2] > 0 and c2_range < RANGE_ATR_MULT * m5_atr[c2]:
            continue

        # -------------------------------------------------------------
        # BULLISH SILVER BULLET SETUP (Seeks BSL in Discount)
        # -------------------------------------------------------------
        if ctx.dol_side == 1 and m5_c[c2] > m5_o[c2]: # Bullish expansion candle
            # Must form Bullish FVG: Low of candle 3 > High of candle 1
            if m5_l[c3] <= m5_h[c1]:
                continue
            
            proximal_entry = float(m5_h[c1])
            ce_midpoint = (float(m5_l[c3]) + float(m5_h[c1])) / 2.0

            # Dealing Range Filter: Entry must be in Discount (< Equilibrium)
            if proximal_entry > ctx.equilibrium:
                continue

            # Lookback for MSS: Candle 2 must break above an opposing confirmed M5 swing high
            p_idx = latest_confirmed_pivot(ph5, c2, right=2)
            if p_idx < 0 or p_idx < c2 - 15:
                continue
            pivot_to_break = float(m5_h[p_idx])

            # Candle 2 body close must break the pivot
            if m5_c[c2] <= pivot_to_break:
                continue

            # Identify the structural manipulation sweep low (anchor)
            anchor_low = float(np.min(m5_l[max(0, c2 - 6) : c2]))
            sl_px = anchor_low - (current_spread * 1.50)
            risk_dist = proximal_entry - sl_px

            if not (sp.min_stop <= risk_dist <= sp.max_stop):
                continue

            tp_px = proximal_entry + TARGET_RR * risk_dist
            rr = TARGET_RR

            return Setup(
                side=1,
                sweep_m5=c1,
                anchor_px=anchor_low,
                c3_m5=c3,
                c3_close_m1=int(m5_m1_end[c3]),
                entry_px=proximal_entry,
                ce_px=ce_midpoint,
                sl_px=sl_px,
                tp_px=tp_px,
                risk_dist=risk_dist,
                rr=rr,
            )

        # -------------------------------------------------------------
        # BEARISH SILVER BULLET SETUP (Seeks SSL in Premium)
        # -------------------------------------------------------------
        elif ctx.dol_side == -1 and m5_c[c2] < m5_o[c2]: # Bearish expansion candle
            # Must form Bearish FVG: High of candle 3 < Low of candle 1
            if m5_h[c3] >= m5_l[c1]:
                continue

            proximal_entry = float(m5_l[c1])
            ce_midpoint = (float(m5_l[c1]) + float(m5_h[c3])) / 2.0

            # Dealing Range Filter: Entry must be in Premium (> Equilibrium)
            if proximal_entry < ctx.equilibrium:
                continue

            # Lookback for MSS: Candle 2 must break below an opposing confirmed M5 swing low
            p_idx = latest_confirmed_pivot(pl5, c2, right=2)
            if p_idx < 0 or p_idx < c2 - 15:
                continue
            pivot_to_break = float(m5_l[p_idx])

            if m5_c[c2] >= pivot_to_break:
                continue

            anchor_high = float(np.max(m5_h[max(0, c2 - 6) : c2]))
            sl_px = anchor_high + (current_spread * 1.50)
            risk_dist = sl_px - proximal_entry

            if not (sp.min_stop <= risk_dist <= sp.max_stop):
                continue

            tp_px = proximal_entry - TARGET_RR * risk_dist
            rr = TARGET_RR

            return Setup(
                side=-1,
                sweep_m5=c1,
                anchor_px=anchor_high,
                c3_m5=c3,
                c3_close_m1=int(m5_m1_end[c3]),
                entry_px=proximal_entry,
                ce_px=ce_midpoint,
                sl_px=sl_px,
                tp_px=tp_px,
                risk_dist=risk_dist,
                rr=rr,
            )

    return None


from v17.setups.c22_silver_bullet import (
    Bars,
    M5Bars,
    build_m5,
    build_daily_df,
    pivot_flags,
    latest_confirmed_pivot,
    execute_trade_m1,
)


def run_slot_c24(
    b: Bars,
    symbol: str,
    window: str,
    start_date: str,
    end_date: str,
    calendar_blackout_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Executes Cycle 24 Silver Bullet Antigravity engine across a date range."""
    sp = SPECS[symbol]
    m5 = build_m5(b)
    daily = build_daily_df(b)
    ph5, pl5 = pivot_flags(m5.h, m5.l, left=2, right=2)

    (sh, sm), (eh, em) = WINDOWS[window]
    (end_h, end_m) = SESSION_ENDS[window]

    ts_dt_ny = pd.to_datetime(b.ts, unit="ns", utc=True).tz_convert(NY)
    days = ts_dt_ny.strftime("%Y-%m-%d").to_numpy()
    unique_days = [d for d in np.unique(days) if start_date <= d <= end_date]

    trades: list[dict] = []

    for day in unique_days:
        ctx = compute_institutional_context(b.ts, b.mid_h, b.mid_l, b.mid_c, day, daily, window)
        if ctx is None:
            continue

        day_start_ns = pd.Timestamp(day).tz_localize(NY).tz_convert("UTC").value
        ws_ns = day_start_ns + (sh * 3600 + sm * 60) * 1_000_000_000
        we_ns = day_start_ns + (eh * 3600 + em * 60) * 1_000_000_000
        send_ns = day_start_ns + (end_h * 3600 + end_m * 60) * 1_000_000_000

        # Calendar News Blackout
        if calendar_blackout_df is not None and not calendar_blackout_df.empty:
            from v17.data.calendar.blackout import SYMBOL_CURRENCY_MAP, is_in_blackout
            currencies = SYMBOL_CURRENCY_MAP.get(symbol, ["USD"])
            if is_in_blackout(ws_ns, calendar_blackout_df, currencies):
                continue

        m5_start_idx = int(np.searchsorted(m5.ts_start, ws_ns))
        m5_end_idx = int(np.searchsorted(m5.ts_close, we_ns))
        if m5_end_idx <= m5_start_idx + 2:
            continue

        i_ws = np.searchsorted(b.ts, ws_ns)
        cur_spread = float(b.ask_c[i_ws] - b.bid_c[i_ws]) if i_ws < len(b.ts) else 0.0001

        setup = find_setup(
            m5_ts_start=m5.ts_start,
            m5_o=m5.o, m5_h=m5.h, m5_l=m5.l, m5_c=m5.c,
            m5_atr=m5.atr, m5_m1_end=m5.m1_end_idx,
            ph5=ph5, pl5=pl5,
            m5_start_idx=m5_start_idx,
            m5_end_idx=m5_end_idx,
            ctx=ctx,
            sp=sp,
            current_spread=cur_spread,
        )

        if setup is None:
            continue

        # Simulate M1 forward fill and outcome
        order_time_i = setup.c3_close_m1
        session_end_i = np.searchsorted(b.ts, send_ns)
        if session_end_i >= len(b.ts):
            session_end_i = len(b.ts) - 1

        fill_i = None
        for k in range(order_time_i + 1, min(len(b.ts), session_end_i)):
            if setup.side == 1:
                # Long: Fills on ASK <= entry
                if b.ask_l[k] <= setup.entry_px:
                    fill_i = k
                    break
                # Cancellation if price violates SL before filling
                if b.bid_l[k] <= setup.sl_px:
                    break
            else:
                # Short: Fills on BID >= entry
                if b.bid_h[k] >= setup.entry_px:
                    fill_i = k
                    break
                if b.ask_h[k] >= setup.sl_px:
                    break

        if fill_i is None:
            continue

        # Execute M1 Trade
        exit_i, reason_code, exit_raw = execute_trade_m1(
            fill_i=fill_i,
            session_end_i=session_end_i,
            side=setup.side,
            sl=setup.sl_px,
            tp=setup.tp_px,
            bid_o=b.bid_o, bid_h=b.bid_h, bid_l=b.bid_l, bid_c=b.bid_c,
            ask_o=b.ask_o, ask_h=b.ask_h, ask_l=b.ask_l, ask_c=b.ask_c,
        )

        # Apply slippage & commission
        if setup.side == 1:
            fill_px = setup.entry_px + sp.slip
            exit_px = exit_raw - sp.slip
            raw_pnl = exit_px - fill_px
        else:
            fill_px = setup.entry_px - sp.slip
            exit_px = exit_raw + sp.slip
            raw_pnl = fill_px - exit_px

        net_pnl = raw_pnl - sp.commission_rt
        net_r = net_pnl / setup.risk_dist

        trades.append({
            "day": day,
            "symbol": symbol,
            "window": window,
            "side": setup.side,
            "entry": setup.entry_px,
            "ce": setup.ce_px,
            "sl": setup.sl_px,
            "tp": setup.tp_px,
            "risk_dist": setup.risk_dist,
            "rr": setup.rr,
            "fill_i": fill_i,
            "exit_i": exit_i,
            "reason": str(reason_code),
            "r": net_r,
        })

    return pd.DataFrame(trades)
