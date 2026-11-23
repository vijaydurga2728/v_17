"""ORB CLASSIC v2 — tighter SL (entry ± 1*ATR) + 1.5R target.

Params changed from orb_classic_probe.py:
  SL_ATR_MULT: 0.5 → used as entry ± 1.0*ATR (not OR_extreme ± 0.5*ATR)
  R_TARGET: 0.5 → 1.5
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
R_TARGET = 1.5
SL_ATR_MULT = 1.0  # entry ± 1.0 * ATR


def _atr14(bid_h, bid_l, bid_c):
    n = len(bid_h)
    tr = np.empty(n)
    tr[0] = bid_h[0] - bid_l[0]
    for i in range(1, n):
        tr[i] = max(
            bid_h[i] - bid_l[i],
            abs(bid_h[i] - bid_c[i - 1]),
            abs(bid_l[i] - bid_c[i - 1]),
        )
    return pd.Series(tr).rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean().to_numpy()


def _session_vwap(bid_c, ask_c, bid_vol, ask_vol):
    mid = (bid_c + ask_c) / 2.0
    vol = bid_vol + ask_vol
    vol_safe = np.where(vol > 0, vol, 1e-9)
    return np.cumsum(mid * vol_safe) / np.cumsum(vol_safe)


def run_one_symbol(symbol: str, bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["_ts_ny"] = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df["_date"] = df["_ts_ny"].dt.date
    df["_hhmm"] = df["_ts_ny"].dt.strftime("%H:%M")

    atr_full = _atr14(
        df["bid_h"].to_numpy(float),
        df["bid_l"].to_numpy(float),
        df["bid_c"].to_numpy(float),
    )

    trades: list[dict] = []

    for date, grp in df.groupby("_date", sort=True):
        grp = grp.sort_values("ts_utc").reset_index(drop=True)
        hhmm = grp["_hhmm"].to_numpy()

        or_mask = (hhmm >= OR_START_ET) & (hhmm < OR_END_ET)
        or_bars = grp[or_mask]
        if len(or_bars) < 10:
            continue
        or_high = float(or_bars["bid_h"].max())
        or_low = float(or_bars["bid_l"].min())

        scan_mask = (hhmm >= OR_END_ET) & (hhmm < SCAN_END_ET)
        scan = grp[scan_mask].reset_index(drop=True)
        if scan.empty:
            continue

        s_bh = scan["bid_h"].to_numpy(float)
        s_bl = scan["bid_l"].to_numpy(float)
        s_bc = scan["bid_c"].to_numpy(float)
        s_ac = scan["ask_c"].to_numpy(float)
        s_ah = scan["ask_h"].to_numpy(float)
        s_ts = scan["ts_utc"].to_numpy(np.int64)
        s_orig_idx = scan.index.to_numpy()

        up_break = np.where(s_bh > or_high)[0]
        dn_break = np.where(s_bl < or_low)[0]
        if len(up_break) == 0 and len(dn_break) == 0:
            continue
        up_i = up_break[0] if len(up_break) else len(scan) + 1
        dn_i = dn_break[0] if len(dn_break) else len(scan) + 1

        if up_i < dn_i:
            direction = "LONG"
            bo_idx = up_i
        else:
            direction = "SHORT"
            bo_idx = dn_i

        cb_end = min(bo_idx + CLOSE_BACK_WINDOW_MIN + 1, len(scan))
        entry_idx = None
        for j in range(bo_idx + 1, cb_end):
            if direction == "LONG":
                if s_bc[j] < or_high:
                    entry_idx = j
                    break
            else:
                if s_bc[j] > or_low:
                    entry_idx = j
                    break
        if entry_idx is None:
            continue

        atr_entry = float(atr_full[int(s_orig_idx[entry_idx])])
        if not np.isfinite(atr_entry) or atr_entry <= 0:
            continue

        if direction == "LONG":
            entry_px = float(s_ac[entry_idx])
            sl_px = entry_px - SL_ATR_MULT * atr_entry  # ← tighter: entry - 1 ATR
            risk = entry_px - sl_px
            if risk <= 0:
                continue
            tp_px = entry_px + R_TARGET * risk  # ← 1.5R target
        else:
            entry_px = float(s_bc[entry_idx])
            sl_px = entry_px + SL_ATR_MULT * atr_entry
            risk = sl_px - entry_px
            if risk <= 0:
                continue
            tp_px = entry_px - R_TARGET * risk

        exit_idx = None
        exit_px = None
        exit_reason = None
        for j in range(entry_idx + 1, len(scan)):
            if direction == "LONG":
                hit_sl = s_bl[j] <= sl_px
                hit_tp = s_ah[j] >= tp_px
            else:
                hit_sl = s_ah[j] >= sl_px
                hit_tp = s_bl[j] <= tp_px
            if hit_sl and hit_tp:
                exit_px, exit_reason, exit_idx = sl_px, "SL", j
                break
            if hit_sl:
                exit_px, exit_reason, exit_idx = sl_px, "SL", j
                break
            if hit_tp:
                exit_px, exit_reason, exit_idx = tp_px, "TP", j
                break

        if exit_idx is None:
            exit_idx = len(scan) - 1
            if direction == "LONG":
                exit_px = float(s_bc[exit_idx])
            else:
                exit_px = float(s_ac[exit_idx])
            exit_reason = "TIME"

        if direction == "LONG":
            pnl_r = (exit_px - entry_px) / risk
        else:
            pnl_r = (entry_px - exit_px) / risk

        trades.append({
            "symbol": symbol, "date": date, "direction": direction,
            "entry_ts_ns": int(s_ts[entry_idx]), "entry_px": entry_px,
            "sl_px": sl_px, "tp_px": tp_px,
            "exit_ts_ns": int(s_ts[exit_idx]), "exit_px": exit_px,
            "exit_reason": exit_reason, "atr_entry": atr_entry, "risk": risk,
            "pnl_r": pnl_r,
        })

    return pd.DataFrame(trades)


def main() -> None:
    results_root = Path("research/results")
    results_root.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    sym = "USATECHIDXUSD"
    print(f"[{time.strftime('%H:%M:%S')}] load {sym}...", flush=True)
    bars = read_bars(root=Path("data"), symbol=sym, partition="dev", dev_only=True)
    print(f"  {len(bars):,} bars", flush=True)

    ts = pd.to_datetime(bars["ts_utc"], utc=True)
    years = (ts.max() - ts.min()).days / 365.25

    print(f"[{time.strftime('%H:%M:%S')}] scan v2 (SL ± 1ATR, TP 1.5R)...", flush=True)
    t_s = time.time()
    trades = run_one_symbol(sym, bars)
    print(f"  {len(trades)} trades in {time.time()-t_s:.1f}s", flush=True)

    trades.to_parquet(results_root / "orb_classic_v2_USATECHIDXUSD.parquet", index=False)

    if len(trades) == 0:
        print("\nNo trades. RED.")
        return

    wins = trades[trades["pnl_r"] > 0]
    losses = trades[trades["pnl_r"] < 0]
    pf = wins["pnl_r"].sum() / abs(losses["pnl_r"].sum()) if abs(losses["pnl_r"].sum()) > 0 else float("inf")
    equity = trades["pnl_r"].cumsum().to_numpy()
    peak = np.maximum.accumulate(equity)
    max_dd = float((peak - equity).max())

    print("\n" + "=" * 72)
    print(f"ORB CLASSIC v2 — RESULTS ({sym})  [SL ±1ATR, TP 1.5R]")
    print("=" * 72)
    print(f"  trades: {len(trades)}")
    print(f"  win rate: {(trades.pnl_r > 0).mean()*100:.1f}%")
    print(f"  profit factor: {pf:.2f}")
    print(f"  mean R: {trades.pnl_r.mean():+.3f}")
    print(f"  sum R: {trades.pnl_r.sum():+.2f}")
    print(f"  max DD (R): {max_dd:.2f}")
    print(f"  trades/year: {len(trades)/years:.1f}")
    print(f"  exits: {trades['exit_reason'].value_counts().to_dict()}")
    print("-" * 72)
    pf_ok = pf >= 1.3
    count_ok = (len(trades) / years) >= 50
    if pf_ok and count_ok:
        print(f"DECISION: GREEN — PF {pf:.2f} >= 1.3 AND {len(trades)/years:.0f} trades/year >= 50")
    else:
        print(f"DECISION: RED — PF {pf:.2f} (need 1.3); trades/year {len(trades)/years:.1f} (need 50)")
    print("-" * 72)
    print(f"Wall clock: {time.time()-t0:.1f}s\n", flush=True)


if __name__ == "__main__":
    main()
