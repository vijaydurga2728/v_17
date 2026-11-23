"""CRT (Candle Range Theory) probe.

Mechanic:
  1. Reference candle = prior H4 candle. Track its high/low.
  2. On H1 bars during the current H4 window: watch for a bar that PIERCES
     the reference H4's high or low (sweep), then CLOSES BACK INSIDE the
     reference H4's range.
  3. Entry: at the closing bar of the pierce-and-close-back. Fire only
     once per H4 reference.
  4. ICT textbook direction: FADE (reversal) — short on upside sweep,
     long on downside sweep.
  5. Test both directions (FADE and CONTINUE) for apples-to-apples
     comparison with paper's finding on ICT direction.

Params:
  - Reference TF: H4 (prior candle).
  - Entry TF: H1.
  - Sweep: wick must clear the reference high/low.
  - Closure: closing price must be back inside the ref candle range.
  - SL: swept extreme ± 0.5 * ATR_14 (paper's min_stop_atr floor).
  - TP: 2R.
  - Horizon: 24 H1 bars after entry.

Symbols: EURUSD, GBPUSD.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from v17.data.parquet_store import read_bars


ATR_PERIOD = 14
MIN_STOP_ATR = 0.5
RR_TARGET = 2.0
HORIZON_BARS = 24


def _resample(m1: pd.DataFrame, freq: str) -> pd.DataFrame:
    df = m1.copy()
    df["_ts"] = pd.to_datetime(df["ts_utc"], utc=True)
    df = df.set_index("_ts").sort_index()
    agg = df.resample(freq, label="left", closed="left").agg(
        ts_utc=("ts_utc", "first"),
        bid_o=("bid_o", "first"),
        bid_h=("bid_h", "max"),
        bid_l=("bid_l", "min"),
        bid_c=("bid_c", "last"),
        ask_o=("ask_o", "first"),
        ask_h=("ask_h", "max"),
        ask_l=("ask_l", "min"),
        ask_c=("ask_c", "last"),
    ).dropna().reset_index(drop=True)
    return agg


def _atr14(h, l, c):
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return pd.Series(tr).rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean().to_numpy()


def run_one_symbol(sym: str, m1: pd.DataFrame, direction: str) -> pd.DataFrame:
    """direction: 'FADE' (reversal — ICT textbook) or 'CONTINUE'."""
    h4 = _resample(m1, "4h")
    h1 = _resample(m1, "1h")

    h4_ts = h4["ts_utc"].to_numpy(np.int64)
    h4_h = h4["bid_h"].to_numpy(float)
    h4_l = h4["bid_l"].to_numpy(float)
    _NS_PER_H4 = 4 * 3_600_000_000_000

    # H1 arrays
    ts = h1["ts_utc"].to_numpy(np.int64)
    bh = h1["bid_h"].to_numpy(float)
    bl = h1["bid_l"].to_numpy(float)
    bc = h1["bid_c"].to_numpy(float)
    ah = h1["ask_h"].to_numpy(float)
    ac = h1["ask_c"].to_numpy(float)
    atr = _atr14(bh, bl, bc)
    n = len(h1)

    trades = []
    last_fired_h4_idx = -1

    for i in range(ATR_PERIOD + 1, n - HORIZON_BARS):
        bar_ts = int(ts[i])
        # Find prior H4 candle: the H4 whose window has fully closed before bar_ts
        pos = np.searchsorted(h4_ts, bar_ts, side="right") - 1
        # Prior H4 = pos-1 (pos is current H4 window)
        prior_idx = pos - 1
        if prior_idx < 0:
            continue
        # Fire max once per prior H4 reference
        if prior_idx == last_fired_h4_idx:
            continue
        ref_high = float(h4_h[prior_idx])
        ref_low = float(h4_l[prior_idx])

        # Check sweep + close-back on this H1 bar
        swept_up = bh[i] > ref_high and bc[i] < ref_high  # wick above ref_high, close back inside
        swept_down = bl[i] < ref_low and bc[i] > ref_low  # wick below ref_low, close back inside

        if not (swept_up or swept_down):
            continue

        if swept_up:
            swept_extreme = float(bh[i])
            textbook_side = "SHORT"  # FADE upside sweep
        else:
            swept_extreme = float(bl[i])
            textbook_side = "LONG"

        if direction == "FADE":
            side = textbook_side
        else:  # CONTINUE
            side = "LONG" if textbook_side == "SHORT" else "SHORT"

        atr_entry = float(atr[i])
        if not np.isfinite(atr_entry) or atr_entry <= 0:
            continue

        if side == "SHORT":
            entry_px = float(bc[i])
            sl_px = swept_extreme + MIN_STOP_ATR * atr_entry
            risk = sl_px - entry_px
            if risk <= 0:
                continue
            tp_px = entry_px - RR_TARGET * risk
        else:
            entry_px = float(ac[i])
            sl_px = swept_extreme - MIN_STOP_ATR * atr_entry
            risk = entry_px - sl_px
            if risk <= 0:
                continue
            tp_px = entry_px + RR_TARGET * risk

        # Walk forward
        exit_idx = None
        exit_px = None
        exit_reason = None
        max_j = min(i + HORIZON_BARS, n)
        for j in range(i + 1, max_j):
            if side == "LONG":
                hit_sl = bl[j] <= sl_px
                hit_tp = ah[j] >= tp_px
            else:
                hit_sl = ah[j] >= sl_px
                hit_tp = bl[j] <= tp_px
            if hit_sl and hit_tp:
                exit_idx, exit_px, exit_reason = j, sl_px, "SL"
                break
            if hit_sl:
                exit_idx, exit_px, exit_reason = j, sl_px, "SL"
                break
            if hit_tp:
                exit_idx, exit_px, exit_reason = j, tp_px, "TP"
                break
        if exit_idx is None:
            exit_idx = max_j - 1
            exit_px = float(bc[exit_idx] if side == "LONG" else ac[exit_idx])
            exit_reason = "TIME"

        pnl_r = ((exit_px - entry_px) / risk) if side == "LONG" else ((entry_px - exit_px) / risk)
        trades.append({
            "symbol": sym, "direction_mode": direction,
            "textbook_side": textbook_side, "side": side,
            "entry_ts_ns": bar_ts, "entry_px": entry_px, "sl_px": sl_px, "tp_px": tp_px,
            "exit_ts_ns": int(ts[exit_idx]), "exit_px": exit_px, "exit_reason": exit_reason,
            "risk": risk, "pnl_r": pnl_r, "atr_entry": atr_entry,
            "ref_high": ref_high, "ref_low": ref_low, "swept_extreme": swept_extreme,
        })
        last_fired_h4_idx = prior_idx

    return pd.DataFrame(trades)


def _summarize(name, df, years):
    n = len(df)
    if n == 0:
        print(f"\n{name}: 0 trades")
        return
    wins = df[df["pnl_r"] > 0]
    losses = df[df["pnl_r"] < 0]
    pf = wins["pnl_r"].sum() / abs(losses["pnl_r"].sum()) if abs(losses["pnl_r"].sum()) > 0 else float("inf")
    equity = df["pnl_r"].cumsum().to_numpy()
    peak = np.maximum.accumulate(equity)
    max_dd = float((peak - equity).max())
    print(f"\n{name}:")
    print(f"  trades: {n} ({n/years:.1f}/year)")
    print(f"  WR: {(df.pnl_r > 0).mean()*100:.1f}%  PF: {pf:.2f}  mean R: {df.pnl_r.mean():+.3f}  sum R: {df.pnl_r.sum():+.2f}")
    print(f"  max DD (R): {max_dd:.2f}  exits: {df['exit_reason'].value_counts().to_dict()}")
    ann_r = (n / years) * df.pnl_r.mean()
    print(f"  Annualized R: {ann_r:+.2f}  → @0.5% risk on $10k: ${ann_r*50:+.0f}/year")


def main():
    results_root = Path("research/results")
    results_root.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    all_rows = []
    for sym in ["EURUSD", "GBPUSD"]:
        print(f"[{time.strftime('%H:%M:%S')}] load {sym}...", flush=True)
        m1 = read_bars(root=Path("data"), symbol=sym, partition="dev", dev_only=True)
        print(f"  {len(m1):,} M1 bars", flush=True)
        years = (pd.to_datetime(m1["ts_utc"].max(), utc=True) - pd.to_datetime(m1["ts_utc"].min(), utc=True)).days / 365.25

        for mode in ["FADE", "CONTINUE"]:
            print(f"[{time.strftime('%H:%M:%S')}] scan {sym} CRT {mode}...", flush=True)
            t_s = time.time()
            df = run_one_symbol(sym, m1, mode)
            print(f"  {len(df)} trades in {time.time()-t_s:.1f}s", flush=True)
            df.to_parquet(results_root / f"crt_{mode}_{sym}.parquet", index=False)
            _summarize(f"{sym} CRT {mode}", df, years)
            all_rows.append(df)

    print(f"\nWall clock: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
