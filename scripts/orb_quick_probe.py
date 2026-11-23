"""ORB reversal quick-probe scanner — standalone, no framework.

Rule set:
  1. Build 30-min opening range from 09:30-10:00 ET bars.
  2. Scan 10:00-11:30 ET for first breakout of OR_high or OR_low.
  3. After a breakout, if a subsequent M1 bar CLOSES back inside the OR within 15 min
     of the breakout bar, enter OPPOSITE direction at that bar's close.
     (Fade the breakout — short on upside break, long on downside break.)
  4. SL = breakout extreme ± 0.5 × ATR_14 (M1 ATR as of the breakout bar).
  5. Target: fixed 0.5R OR VWAP touch, whichever is further (take profit at the farther).
     Simplified here: 0.5R primary; if session VWAP is further than 0.5R, extend to VWAP.
  6. Fills: use bid/ask sides. LONG entry = ask, exit = bid. SHORT symmetric.
  7. Hard exit at 11:30 ET (end of scan window).
  8. One trade per (symbol, day).

Report: per-symbol + aggregate counts, WR, PF, expectancy, R:R realized, trade/year.
Decision: GREEN if PF >= 1.3 AND trades/year/symbol >= 50; else RED.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from v17.data.parquet_store import read_bars


ATR_PERIOD = 14
OR_START_ET = "09:30"
OR_END_ET = "10:00"
SCAN_END_ET = "11:30"
CLOSE_BACK_WINDOW_MIN = 15
R_TARGET = 0.5  # 0.5R primary
SL_ATR_MULT = 0.5


def _atr14(bid_h: np.ndarray, bid_l: np.ndarray, bid_c: np.ndarray) -> np.ndarray:
    n = len(bid_h)
    tr = np.empty(n)
    tr[0] = bid_h[0] - bid_l[0]
    for i in range(1, n):
        tr[i] = max(
            bid_h[i] - bid_l[i],
            abs(bid_h[i] - bid_c[i - 1]),
            abs(bid_l[i] - bid_c[i - 1]),
        )
    atr = pd.Series(tr).rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean().to_numpy()
    return atr


def _session_vwap(bid_c: np.ndarray, ask_c: np.ndarray, bid_vol: np.ndarray, ask_vol: np.ndarray) -> np.ndarray:
    """Rolling intra-session VWAP using mid prices and combined volumes."""
    mid = (bid_c + ask_c) / 2.0
    vol = bid_vol + ask_vol
    # Avoid 0-vol bars contributing NaN; add tiny epsilon for stability.
    vol_safe = np.where(vol > 0, vol, 1e-9)
    cum_vp = np.cumsum(mid * vol_safe)
    cum_v = np.cumsum(vol_safe)
    return cum_vp / cum_v


def run_one_symbol(symbol: str, bars: pd.DataFrame) -> pd.DataFrame:
    """Scan ORB reversal for one symbol across all dev session days.

    Returns DataFrame of trades with columns:
      date, side, entry_ts_ns, entry_px, sl_px, tp_px, exit_ts_ns, exit_px,
      exit_reason, pnl_r.
    """
    # Convert to NY time once
    df = bars.copy()
    df["_ts_ny"] = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df["_date"] = df["_ts_ny"].dt.date
    df["_hhmm"] = df["_ts_ny"].dt.strftime("%H:%M")

    # Pre-compute ATR on full series
    bid_h = df["bid_h"].to_numpy(dtype=float)
    bid_l = df["bid_l"].to_numpy(dtype=float)
    bid_c = df["bid_c"].to_numpy(dtype=float)
    bid_o = df["bid_o"].to_numpy(dtype=float)
    ask_c = df["ask_c"].to_numpy(dtype=float)
    ask_h = df["ask_h"].to_numpy(dtype=float)
    ask_l = df["ask_l"].to_numpy(dtype=float)
    bid_vol = df["bid_volume"].to_numpy(dtype=float)
    ask_vol = df["ask_volume"].to_numpy(dtype=float)
    atr_full = _atr14(bid_h, bid_l, bid_c)

    trades: list[dict] = []

    for date, grp in df.groupby("_date", sort=True):
        grp = grp.sort_values("ts_utc").reset_index(drop=True)
        hhmm = grp["_hhmm"].to_numpy()

        # OR bars: 09:30-10:00 ET
        or_mask = (hhmm >= OR_START_ET) & (hhmm < OR_END_ET)
        or_bars = grp[or_mask]
        if len(or_bars) < 10:
            continue  # incomplete OR (likely non-trading or truncated day)
        or_high = float(or_bars["bid_h"].max())
        or_low = float(or_bars["bid_l"].min())

        # Scan window 10:00-11:30 ET
        scan_mask = (hhmm >= OR_END_ET) & (hhmm < SCAN_END_ET)
        scan = grp[scan_mask].reset_index(drop=True)
        if scan.empty:
            continue

        # Vectorized breakout detection: first bar whose bid_h > OR_high or bid_l < OR_low
        s_bh = scan["bid_h"].to_numpy(dtype=float)
        s_bl = scan["bid_l"].to_numpy(dtype=float)
        s_bc = scan["bid_c"].to_numpy(dtype=float)
        s_bo = scan["bid_o"].to_numpy(dtype=float)
        s_ac = scan["ask_c"].to_numpy(dtype=float)
        s_ah = scan["ask_h"].to_numpy(dtype=float)
        s_al = scan["ask_l"].to_numpy(dtype=float)
        s_ts = scan["ts_utc"].to_numpy(dtype=np.int64)
        s_orig_idx = scan.index.to_numpy()

        # Find first breakout
        up_break = np.where(s_bh > or_high)[0]
        dn_break = np.where(s_bl < or_low)[0]
        if len(up_break) == 0 and len(dn_break) == 0:
            continue
        up_i = up_break[0] if len(up_break) else len(scan) + 1
        dn_i = dn_break[0] if len(dn_break) else len(scan) + 1
        if up_i < dn_i:
            direction = "SHORT"  # fade upside break → SHORT
            bo_idx = up_i
            breakout_extreme = float(s_bh[bo_idx])
        else:
            direction = "LONG"   # fade downside break → LONG
            bo_idx = dn_i
            breakout_extreme = float(s_bl[bo_idx])

        # Look for close-back-inside within 15 min after breakout
        cb_window_end = min(bo_idx + CLOSE_BACK_WINDOW_MIN + 1, len(scan))
        entry_idx = None
        for j in range(bo_idx + 1, cb_window_end):
            if direction == "SHORT":
                # Short entry: bar closes back INSIDE (below OR_high)
                if s_bc[j] < or_high:
                    entry_idx = j
                    break
            else:
                # Long entry: bar closes back INSIDE (above OR_low)
                if s_bc[j] > or_low:
                    entry_idx = j
                    break
        if entry_idx is None:
            continue

        # Entry price: fade direction using appropriate fill side
        # SHORT: sell at bid_c; LONG: buy at ask_c.
        if direction == "SHORT":
            entry_px = float(s_bc[entry_idx])
            # ATR at entry bar via original-index lookup
            atr_entry = float(atr_full[int(s_orig_idx[entry_idx])])
            if not np.isfinite(atr_entry) or atr_entry <= 0:
                continue
            sl_px = breakout_extreme + SL_ATR_MULT * atr_entry
            risk = sl_px - entry_px
            if risk <= 0:
                continue
            tp_px_0_5r = entry_px - R_TARGET * risk
        else:
            entry_px = float(s_ac[entry_idx])
            atr_entry = float(atr_full[int(s_orig_idx[entry_idx])])
            if not np.isfinite(atr_entry) or atr_entry <= 0:
                continue
            sl_px = breakout_extreme - SL_ATR_MULT * atr_entry
            risk = entry_px - sl_px
            if risk <= 0:
                continue
            tp_px_0_5r = entry_px + R_TARGET * risk

        # Session VWAP on this day (cumulative from day start)
        day_start_mask = hhmm >= "09:30"  # from NY open
        day_bars = grp[day_start_mask].reset_index(drop=True)
        d_bc = day_bars["bid_c"].to_numpy(dtype=float)
        d_ac = day_bars["ask_c"].to_numpy(dtype=float)
        d_bv = day_bars["bid_volume"].to_numpy(dtype=float)
        d_av = day_bars["ask_volume"].to_numpy(dtype=float)
        d_ts = day_bars["ts_utc"].to_numpy(dtype=np.int64)
        vwap_series = _session_vwap(d_bc, d_ac, d_bv, d_av)

        # VWAP value at entry time
        entry_ts = int(s_ts[entry_idx])
        pos_in_day = int(np.searchsorted(d_ts, entry_ts, side="left"))
        if pos_in_day >= len(vwap_series):
            vwap_at_entry = float(vwap_series[-1])
        else:
            vwap_at_entry = float(vwap_series[pos_in_day])

        # Target: 0.5R or VWAP, whichever is further (favorable direction).
        if direction == "SHORT":
            tp_vwap = vwap_at_entry
            if tp_vwap < entry_px:
                tp_px = min(tp_px_0_5r, tp_vwap)
            else:
                tp_px = tp_px_0_5r
        else:
            tp_vwap = vwap_at_entry
            if tp_vwap > entry_px:
                tp_px = max(tp_px_0_5r, tp_vwap)
            else:
                tp_px = tp_px_0_5r

        # Walk forward from entry_idx+1 to scan end (11:30). SL/TP hit first.
        # SHORT: SL hit if bar's ask_h >= sl_px; TP hit if bar's bid_l <= tp_px.
        # LONG: SL hit if bar's bid_l <= sl_px; TP hit if bar's ask_h >= tp_px.
        exit_idx = None
        exit_px = None
        exit_reason = None
        for j in range(entry_idx + 1, len(scan)):
            if direction == "SHORT":
                hit_sl = s_ah[j] >= sl_px
                hit_tp = s_bl[j] <= tp_px
                if hit_sl and hit_tp:
                    # Conservative: assume SL first
                    exit_px = sl_px
                    exit_reason = "SL"
                    exit_idx = j
                    break
                if hit_sl:
                    exit_px = sl_px
                    exit_reason = "SL"
                    exit_idx = j
                    break
                if hit_tp:
                    exit_px = tp_px
                    exit_reason = "TP"
                    exit_idx = j
                    break
            else:
                hit_sl = s_bl[j] <= sl_px
                hit_tp = s_ah[j] >= tp_px
                if hit_sl and hit_tp:
                    exit_px = sl_px
                    exit_reason = "SL"
                    exit_idx = j
                    break
                if hit_sl:
                    exit_px = sl_px
                    exit_reason = "SL"
                    exit_idx = j
                    break
                if hit_tp:
                    exit_px = tp_px
                    exit_reason = "TP"
                    exit_idx = j
                    break

        if exit_idx is None:
            # Time exit at last bar of scan window
            exit_idx = len(scan) - 1
            if direction == "SHORT":
                exit_px = float(s_ac[exit_idx])  # buy to cover at ask
            else:
                exit_px = float(s_bc[exit_idx])  # sell to close at bid
            exit_reason = "TIME"

        # Realized pnl_r (R-multiples relative to initial risk)
        if direction == "SHORT":
            pnl_r = (entry_px - exit_px) / risk
        else:
            pnl_r = (exit_px - entry_px) / risk

        trades.append({
            "symbol": symbol,
            "date": date,
            "direction": direction,
            "or_high": or_high, "or_low": or_low,
            "breakout_extreme": breakout_extreme,
            "entry_ts_ns": entry_ts,
            "entry_px": entry_px, "sl_px": sl_px, "tp_px": tp_px,
            "exit_ts_ns": int(s_ts[exit_idx]),
            "exit_px": exit_px, "exit_reason": exit_reason,
            "atr_entry": atr_entry, "risk": risk,
            "pnl_r": pnl_r,
        })

    return pd.DataFrame(trades)


def _summarize(name: str, df: pd.DataFrame, years: float) -> dict:
    n = len(df)
    if n == 0:
        return {"name": name, "trades": 0, "wr": None, "pf": None, "mean_r": None,
                "trades_per_year": 0.0}
    wins = df[df["pnl_r"] > 0]
    losses = df[df["pnl_r"] < 0]
    pf = wins["pnl_r"].sum() / abs(losses["pnl_r"].sum()) if abs(losses["pnl_r"].sum()) > 0 else float("inf")
    exits = df["exit_reason"].value_counts().to_dict()
    equity = df["pnl_r"].cumsum().to_numpy()
    peak = np.maximum.accumulate(equity)
    max_dd_r = float((peak - equity).max())
    return {
        "name": name,
        "trades": n,
        "wr": float((df["pnl_r"] > 0).mean()),
        "pf": float(pf),
        "mean_r": float(df["pnl_r"].mean()),
        "sum_r": float(df["pnl_r"].sum()),
        "max_dd_r": max_dd_r,
        "trades_per_year": n / years,
        "exit_mix": exits,
    }


def main() -> None:
    results_root = Path("research/results")
    results_root.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    symbols = ["USATECHIDXUSD", "USA500IDXUSD"]
    all_trades = []
    per_sym_summary = []

    # Dev data: 2015-01-01 to 2024-12-31 (sealed holdout starts 2025-01-01).
    # Years in dev = 10 for FX, but indices data starts 2015-01-01 too.
    # Use actual coverage for trades/year denominator.
    for sym in symbols:
        print(f"[{time.strftime('%H:%M:%S')}] load {sym} dev bars...", flush=True)
        bars = read_bars(root=Path("data"), symbol=sym, partition="dev", dev_only=True)
        print(f"  {len(bars):,} bars", flush=True)

        ts = pd.to_datetime(bars["ts_utc"], utc=True)
        years = max(1e-6, (ts.max() - ts.min()).days / 365.25)

        print(f"[{time.strftime('%H:%M:%S')}] scan {sym} ORB...", flush=True)
        t_s = time.time()
        trades = run_one_symbol(sym, bars)
        dt = time.time() - t_s
        print(f"  {len(trades)} trades in {dt:.1f}s", flush=True)

        all_trades.append(trades)
        per_sym_summary.append(_summarize(sym, trades, years))
        trades.to_parquet(results_root / f"orb_quick_{sym}.parquet", index=False)

    combined = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    agg_years = 10.0  # 2015-2024
    agg = _summarize("AGGREGATE", combined, agg_years * len(symbols))  # trade-years across both

    total_wall = time.time() - t0
    print("\n" + "=" * 72)
    print("ORB QUICK PROBE — RESULTS")
    print("=" * 72)
    for s in per_sym_summary + [agg]:
        print(f"\n{s['name']}")
        print(f"  trades: {s['trades']}")
        if s['trades'] == 0:
            continue
        print(f"  win rate: {s['wr']*100:.1f}%")
        print(f"  profit factor: {s['pf']:.2f}")
        print(f"  mean R: {s['mean_r']:+.3f}")
        print(f"  sum R: {s['sum_r']:+.2f}")
        print(f"  max DD (R): {s['max_dd_r']:.2f}")
        print(f"  trades/year: {s['trades_per_year']:.1f}")
        print(f"  exits: {s.get('exit_mix', {})}")

    # Green/red decision
    if agg['trades'] == 0:
        decision = "RED — no trades generated"
    else:
        pf_ok = agg['pf'] >= 1.3
        count_ok = agg['trades_per_year'] >= 100  # 50/symbol/year × 2 symbols
        if pf_ok and count_ok:
            decision = f"GREEN — PF {agg['pf']:.2f} >= 1.3 AND {agg['trades_per_year']:.0f} trades/year across 2 symbols >= 100"
        else:
            decision = f"RED — PF {agg['pf']:.2f} (need 1.3), trades/year {agg['trades_per_year']:.1f} (need 100)"
    print("\n" + "-" * 72)
    print(f"DECISION: {decision}")
    print("-" * 72)
    print(f"Total wall-clock: {total_wall:.1f}s\n", flush=True)


if __name__ == "__main__":
    main()
