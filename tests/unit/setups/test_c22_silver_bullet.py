"""Unit tests for Cycle 22: Institutional Silver Bullet (Zero-Lookahead Reform)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from v17.setups import c22_silver_bullet as sb


def _make_m1_bars(n_bars: int = 100, base_px: float = 1.0800, start_dt: str = "2024-01-08 09:00:00") -> sb.Bars:
    t0 = pd.Timestamp(start_dt, tz="America/New_York").tz_convert("UTC").value
    ts = np.array([t0 + k * 60_000_000_000 for k in range(n_bars)], dtype=np.int64)
    px = np.full(n_bars, base_px, dtype=np.float64)
    spread = 0.0001
    return sb.Bars(
        ts=ts,
        bid_o=px,
        bid_h=px + 0.0005,
        bid_l=px - 0.0005,
        bid_c=px,
        ask_o=px + spread,
        ask_h=px + spread + 0.0005,
        ask_l=px + spread - 0.0005,
        ask_c=px + spread,
        mid_o=px + spread / 2,
        mid_h=px + spread / 2 + 0.0005,
        mid_l=px + spread / 2 - 0.0005,
        mid_c=px + spread / 2,
        atr=np.full(n_bars, 0.0005),
    )


def test_m5_bar_aggregation():
    """Verify that M1 bars aggregate to correct M5 bars and timestamps."""
    b = _make_m1_bars(n_bars=20, base_px=1.1000)
    m5 = sb.build_m5(b)
    
    # 20 M1 bars -> 4 M5 bars
    assert len(m5.o) == 4
    assert m5.ts_close[0] - m5.ts_start[0] == 5 * 60_000_000_000
    assert m5.m1_end_idx[0] == 4
    assert m5.m1_end_idx[1] == 9


def test_m5_fractal_pivots_no_lookahead():
    """Verify strict pivot confirmation delay."""
    # Peak at index 2
    h = np.array([10.0, 11.0, 15.0, 12.0, 11.0, 13.0, 14.0], dtype=np.float64)
    l = np.array([8.0, 9.0, 10.0, 9.0, 8.0, 9.0, 10.0], dtype=np.float64)
    ph, pl = sb.pivot_flags(h, l, left=2, right=2)
    
    assert bool(ph[2]) is True
    # At bar index 4, right-side bars are not closed before bar starts -> not visible
    assert sb.latest_confirmed_pivot(ph, 4, right=2) == -1
    # At bar index 5, bar 4 is closed -> visible
    assert sb.latest_confirmed_pivot(ph, 5, right=2) == 2


def test_adr_exhaustion_gate():
    """Verify setups are blocked when intraday range >= 80% ADR."""
    # ADR 10 is 0.0100 (100 pips). Current range is 85 pips (0.0085).
    ctx = sb.DayContext(
        pdh=1.0900,
        pdl=1.0800,
        adr10=0.0100,
        asia_h=1.0880,
        asia_l=1.0820,
        dol_side=1,
        adr_exhausted=True,  # 85% of ADR
    )
    m5 = _make_m1_bars(n_bars=30)
    m5_bars = sb.build_m5(m5)
    ph, pl = sb.pivot_flags(m5_bars.h, m5_bars.l)
    sp = sb.SPECS["EURUSD"]
    
    setup = sb.find_setup(m5_bars, ph, pl, 0, len(m5_bars.o), ctx, sp, 0.0001)
    assert setup is None, "Setup must be blocked on ADR exhaustion!"


def test_unified_impulse_bullish_setup():
    """Verify end-to-end detection of a clean M5 sweep + MSS + FVG setup."""
    # Hand-craft 15 M5 bars:
    # 0, 1: setup swings
    # 2: swing low at 1.0790
    # 3, 4: bounce to 1.0820 (swing high at 1.0820)
    # 5: bar 5 confirms swing low at 2 (k=2, right=2 => confirmed at 5)
    # 6: bar 6 confirms swing high at 4 (k=4, right=2 => confirmed at 7)
    # 7: sweep of swing low 1.0790 -> low drops to 1.0780
    # 8: displacement candle (body >= 60%, breaks swing high 1.0820, closes at 1.0840)
    # 9: candle 3 completes FVG: low=1.0830 > high[7]=1.0800
    
    n = 15
    o = np.full(n, 1.0810)
    h = np.full(n, 1.0815)
    l = np.full(n, 1.0805)
    c = np.full(n, 1.0810)
    
    # Swing low at k=2
    l[2] = 1.0790
    o[2], c[2], h[2] = 1.0800, 1.0795, 1.0805
    
    # Swing high at k=4
    h[4] = 1.0820
    o[4], c[4], l[4] = 1.0810, 1.0818, 1.0805
    
    # Bar 7: sweeps low 1.0790
    l[7] = 1.0780
    h[7] = 1.0800
    o[7], c[7] = 1.0795, 1.0785
    
    # Bar 8: displacement breaking swing high 1.0820
    o[8] = 1.0785
    l[8] = 1.0783
    c[8] = 1.0840
    h[8] = 1.0842
    
    # Bar 9: FVG confirmation: low=1.0825 > high[7]=1.0800
    o[9] = 1.0840
    h[9] = 1.0850
    l[9] = 1.0825
    c[9] = 1.0845
    
    m1_end = np.arange(4, 4 + n * 5, 5, dtype=np.int64)
    ts_start = np.arange(0, n * 300_000_000_000, 300_000_000_000, dtype=np.int64)
    ts_close = ts_start + 300_000_000_000
    atr = np.full(n, 0.0010)
    
    m5 = sb.M5Bars(ts_start, ts_close, o, h, l, c, atr, m1_end)
    ph, pl = sb.pivot_flags(m5.h, m5.l, left=2, right=2)
    
    ctx = sb.DayContext(
        pdh=1.0900,
        pdl=1.0750,
        adr10=0.0100,
        asia_h=1.0850,
        asia_l=1.0790,
        dol_side=1,  # Bullish
        adr_exhausted=False,
    )
    sp = sb.SPECS["EURUSD"]
    
    setup = sb.find_setup(m5, ph, pl, m5_start_idx=0, m5_end_idx=12, ctx=ctx, sp=sp, current_spread=0.0001)
    
    assert setup is not None, "Failed to detect unified bullish setup"
    assert setup.side == 1
    assert setup.entry_px == 1.0800  # high of candle 7 (proximal edge)
    # SL is anchor 1.0780 - 1.5 * spread (0.0001) = 1.07785
    assert setup.sl_px == pytest.approx(1.0780 - 1.5 * 0.0001)
    assert setup.rr >= 1.5


def test_m1_execution_pessimistic_tie_break():
    """Verify same-bar SL/TP tie break gives SL win."""
    bid_o = np.array([1.0800, 1.0800])
    bid_h = np.array([1.0805, 1.0850])  # Touches TP (1.0840)
    bid_l = np.array([1.0795, 1.0750])  # Touches SL (1.0770)
    bid_c = np.array([1.0800, 1.0810])
    ask_o = bid_o + 0.0001
    ask_h = bid_h + 0.0001
    ask_l = bid_l + 0.0001
    ask_c = bid_c + 0.0001
    
    exit_i, reason, px = sb.execute_trade_m1(
        fill_i=0,
        session_end_i=1,
        side=1,
        sl=1.0770,
        tp=1.0840,
        bid_o=bid_o,
        bid_h=bid_h,
        bid_l=bid_l,
        bid_c=bid_c,
        ask_o=ask_o,
        ask_h=ask_h,
        ask_l=ask_l,
        ask_c=ask_c,
    )
    assert reason == 1, "Pessimistic tie-break must result in SL (reason 1)"
    assert px == 1.0770
