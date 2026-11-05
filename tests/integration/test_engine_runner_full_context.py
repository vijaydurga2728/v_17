"""Integration test: craft a scenario that fires exactly one SB-NYAM-CE trade.

Scenario: EURUSD on 2018-03-15.

D1 bias construction:
  - 42 trading days from 2018-02-01 to 2018-03-14 have zigzag-bullish D1 closes
    (trend 1.07→1.11 plus a 7-day sin oscillation with amplitude 0.005).
  - This produces >= 2 pivot highs (HH) and >= 2 pivot lows (HL) in the last 20
    days, satisfying _classify_structure_sb_a1 as BULLISH.
  - Final D1 close > EMA20 (also satisfied by the ascending trend).

Intraday 2018-03-15 (10:00-11:00 NY window):
  - All intraday bars have bid_l=1.1000, bid_h=1.1001 (tight; ATR_14 ≈ 0.0001).
  - 06:00 NY bar: bid_l=1.0999 → session_low = 1.0999.
  - 09:00 NY bar: bid_h=1.1050 → session_high = 1.1050 (opposing target).
  - 10:02 NY bar: bid_h=1.1001 (H_{i-2} for displacement FVG at i=10:04).
  - 10:03 NY bar: bid_l=1.0998 < session_low(1.0999) → sweep confirmed,
                  sweep_extreme = 1.0998.
  - 10:04 NY bar: bid_l=1.1002 > H_{i-2}(1.1001) → bullish FVG [1.1001,1.1002],
                  CE=1.10015. range=0.0008, body=0.0007, ratio=0.875,
                  range >> 1.5×atr_14(0.0001).
  - 10:10 NY bar: bid_l=1.1001 ≤ CE(1.10015) ≤ bid_h=1.1003 → CE fill.

SL/TP:
  - raw_sl = sweep_extreme(1.0998) - buf_min(0.0002) = 1.0996
  - distance = 1.10015 - 1.0996 = 0.00055 ≤ buf_max(0.0015) ✓
  - opposing = session_high = 1.1050
  - reward = 1.1050 - 1.10015 = 0.00485, R:R = 8.8 ≥ 1.5 ✓
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import run_engine_oos
from v17.backtest.walkforward import Fold
from v17.setups.sb_engines import ENGINE_CATALOG


def _synth_eurusd_scenario() -> pd.DataFrame:
    """Generate M1 bars for EURUSD, 2018-02-01 through 2018-03-16.

    Prior-day M1 bars produce zigzag-bullish D1 closes so compute_d1_bias
    returns BULLISH on 2018-03-15. Intraday bars on 2018-03-15 are engineered
    to trigger sweep + displacement + FVG + CE fill.
    """
    # ------------------------------------------------------------------ #
    # Build a zigzag-bullish target close for each of 42 NY trading days. #
    # Day indices 0..41 map to 2018-02-01..2018-03-14 NY.               #
    # ------------------------------------------------------------------ #
    n_days = 42
    t = np.arange(n_days, dtype=float)
    trend = 1.0700 + t * (1.1100 - 1.0700) / (n_days - 1)
    osc = 0.005 * np.sin(2 * np.pi * t / 7)
    day_close_targets = trend + osc  # shape (42,)

    # M1 timestamps for the full range
    start_utc = pd.Timestamp("2018-02-01 00:00:00", tz="UTC")
    end_utc = pd.Timestamp("2018-03-16 00:00:00", tz="UTC")
    ts_all = pd.date_range(start_utc, end_utc, freq="min", inclusive="left")
    n_all = len(ts_all)

    # Assign M1 bar closes based on the NY-day target.
    # For each M1 bar, find its NY date, look up the target close for that date.
    ny_dates_all = ts_all.tz_convert("America/New_York").normalize().tz_localize(None)
    # Build mapping from NY date → target close (for the 42 prior days)
    ny_day_start = pd.Timestamp("2018-02-01").normalize()
    day_closes: dict[pd.Timestamp, float] = {}
    for d_idx in range(n_days):
        ny_day = ny_day_start + pd.Timedelta(days=d_idx)
        day_closes[ny_day] = float(day_close_targets[d_idx])

    bid_c = np.empty(n_all)
    for i, ny_d in enumerate(ny_dates_all):
        bid_c[i] = day_closes.get(ny_d, 1.1100)  # 2018-03-15 day gets 1.1100

    bid_o = bid_c - 0.00002
    bid_h = bid_c + 0.00005
    bid_l = bid_c - 0.00005

    # ------------------------------------------------------------------ #
    # Override 2018-03-15 intraday bars (04:00–15:01 UTC covers NY window) #
    # ------------------------------------------------------------------ #
    # NY 2018-03-15: UTC 04:00–24:00. We override 04:00–15:00 UTC (pre-window
    # + window) to get a controlled session_low / session_high.
    override_start = pd.Timestamp("2018-03-15 04:00:00", tz="UTC")
    override_end = pd.Timestamp("2018-03-15 15:01:00", tz="UTC")
    override_mask = (ts_all >= override_start) & (ts_all < override_end)
    override_idx = np.where(override_mask)[0]

    for gi in override_idx:
        bid_o[gi] = 1.1000
        bid_h[gi] = 1.1001
        bid_l[gi] = 1.1000
        bid_c[gi] = 1.1001

    # NY timestamps for the overridden range
    override_ts_ny = ts_all[override_mask].tz_convert("America/New_York")

    def _apply(hhmm: str, o: float, h: float, l: float, c: float) -> None:
        local_mask = override_ts_ny.strftime("%H:%M") == hhmm
        for gi in override_idx[local_mask]:
            bid_o[gi] = o
            bid_h[gi] = h
            bid_l[gi] = l
            bid_c[gi] = c

    # 06:00 NY: session_low = 1.0999
    _apply("06:00", 1.1000, 1.1001, 1.0999, 1.1001)
    # 09:00 NY: session_high = 1.1050 (opposing target, above entry 1.10015)
    _apply("09:00", 1.1001, 1.1050, 1.1000, 1.1049)
    # 10:02 NY: H_{i-2}=1.1001
    _apply("10:02", 1.1000, 1.1001, 1.1000, 1.1001)
    # 10:03 NY: sweep bar (bid_l=1.0998 < session_low 1.0999)
    _apply("10:03", 1.1000, 1.1001, 1.0998, 1.1000)
    # 10:04 NY: displacement — bid_l=1.1002 > H_{i-2}=1.1001 → bullish FVG
    # range=0.0008, body=|1.1009-1.1002|=0.0007, ratio=0.875
    _apply("10:04", 1.1002, 1.1010, 1.1002, 1.1009)
    # 10:10 NY: CE fill — bid_l=1.1001 ≤ CE(1.10015) ≤ bid_h=1.1003
    _apply("10:10", 1.1001, 1.1003, 1.1001, 1.1003)

    ask_spread = 0.00002
    df = pd.DataFrame({
        "ts_utc": ts_all.astype("int64"),
        "symbol": "EURUSD",
        "bid_o": bid_o,
        "bid_h": bid_h,
        "bid_l": bid_l,
        "bid_c": bid_c,
        "ask_o": bid_o + ask_spread,
        "ask_h": bid_h + ask_spread,
        "ask_l": bid_l + ask_spread,
        "ask_c": bid_c + ask_spread,
        "spread_mid": np.full(n_all, ask_spread),
    })
    return df


def test_crafted_scenario_fires_at_least_one_long_trade_on_sb_nyam_ce():
    """Crafted scenario must fire >= 1 LONG EURUSD trade with real SL/TP."""
    bars = _synth_eurusd_scenario()
    cal = pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"),
        "currency": pd.array([], dtype=object),
        "impact": pd.array([], dtype=object),
    })
    fold = Fold(
        fold_id=1,
        train_start=int(pd.Timestamp("2015-01-01", tz="UTC").value),
        train_end=int(pd.Timestamp("2017-12-31 23:59:59", tz="UTC").value),
        oos_start=int(pd.Timestamp("2018-01-01", tz="UTC").value),
        oos_end=int(pd.Timestamp("2019-01-01", tz="UTC").value),
    )
    cfg = next(c for c in ENGINE_CATALOG if c.engine_id == "SB-NYAM-CE")

    log = run_engine_oos(config=cfg, bars=bars, calendar=cal, fold=fold)

    assert log.engine_id == "SB-NYAM-CE"
    assert log.fold_id == 1
    # At least one trade fires on the crafted day.
    assert len(log.trades) >= 1, (
        f"Expected >= 1 trade, got {len(log.trades)}. "
        "Check D1 bias, sweep, displacement, FVG, fill, or SL/TP gates."
    )
    long_trades = [t for t in log.trades if t.side == "LONG" and t.symbol == "EURUSD"]
    assert len(long_trades) >= 1, (
        f"Got {len(log.trades)} trade(s) but none LONG EURUSD: {log.trades}"
    )
    t = long_trades[0]
    # SL/TP sentinels replaced by compute_sl_tp
    assert t.sl_price > 0, f"sl_price still sentinel 0: {t}"
    assert t.tp_price > 0, f"tp_price still sentinel 0: {t}"
    assert t.r_multiple >= 1.5, f"r_multiple {t.r_multiple:.3f} < 1.5"
