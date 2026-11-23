"""Gap-fade probe v2 — causal SL (fix lookahead bug from v1).

Only change vs v1: SL uses bars 09:30 .. 09:34 (strictly pre-entry).
Entry remains at 09:35 bar's open.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from v17.data.parquet_store import read_bars


ATR_PERIOD = 14
MIN_GAP_PCT = 0.003
SL_ATR_MULT = 0.3
PRE_ENTRY_START = "09:30"
PRE_ENTRY_END = "09:35"   # strictly BEFORE 09:35 (so 09:30-09:34 inclusive)
ENTRY_HHMM = "09:35"
HARD_EXIT_ET = "15:30"


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


def run_one_symbol(symbol, bars):
    df = bars.copy()
    df["_ts_ny"] = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df["_date"] = df["_ts_ny"].dt.date
    df["_hhmm"] = df["_ts_ny"].dt.strftime("%H:%M")

    atr_full = _atr14(
        df["bid_h"].to_numpy(float),
        df["bid_l"].to_numpy(float),
        df["bid_c"].to_numpy(float),
    )

    # Prior close (last bar at/before 16:00) per date
    prior_mask = df["_hhmm"].to_numpy() <= "16:00"
    by_date_last = df[prior_mask].groupby("_date").agg(close=("bid_c", "last")).sort_index()
    dates_sorted = list(by_date_last.index)
    date_to_prior_close = {}
    for i, d in enumerate(dates_sorted):
        if i == 0:
            continue
        date_to_prior_close[d] = float(by_date_last.iloc[i - 1]["close"])

    trades = []
    skipped_small = 0

    for date, grp in df.groupby("_date", sort=True):
        prior_close = date_to_prior_close.get(date)
        if prior_close is None:
            continue

        grp = grp.sort_values("ts_utc").reset_index(drop=True)
        hhmm = grp["_hhmm"].to_numpy()

        # Pre-entry window: 09:30 .. 09:34 (strictly before 09:35)
        pre_mask = (hhmm >= PRE_ENTRY_START) & (hhmm < PRE_ENTRY_END)
        pre = grp[pre_mask]
        if pre.empty:
            continue
        today_open = float(pre["bid_o"].iloc[0])

        gap = today_open - prior_close
        gap_pct = gap / prior_close if prior_close != 0 else 0.0
        if abs(gap_pct) < MIN_GAP_PCT:
            skipped_small += 1
            continue

        # CAUSAL: extremes from bars 09:30-09:34 only
        pre_high = float(pre["bid_h"].max())
        pre_low = float(pre["bid_l"].min())

        entry_bars = grp[grp["_hhmm"] == ENTRY_HHMM]
        if entry_bars.empty:
            continue
        entry_row = entry_bars.iloc[0]
        entry_full_idx = entry_bars.index[0]
        atr_entry = float(atr_full[int(entry_full_idx)])
        if not np.isfinite(atr_entry) or atr_entry <= 0:
            continue

        direction = "SHORT" if gap > 0 else "LONG"
        entry_ts = int(entry_row["ts_utc"])

        if direction == "SHORT":
            entry_px = float(entry_row["bid_o"])
            sl_px = pre_high + SL_ATR_MULT * atr_entry
            risk = sl_px - entry_px
            if risk <= 0:
                continue
            tp_px = prior_close
            if tp_px >= entry_px:
                continue
        else:
            entry_px = float(entry_row["ask_o"])
            sl_px = pre_low - SL_ATR_MULT * atr_entry
            risk = entry_px - sl_px
            if risk <= 0:
                continue
            tp_px = prior_close
            if tp_px <= entry_px:
                continue

        after_entry = grp[(grp["_hhmm"] > ENTRY_HHMM) & (grp["_hhmm"] < HARD_EXIT_ET)].reset_index(drop=True)
        if after_entry.empty:
            continue

        s_bl = after_entry["bid_l"].to_numpy(float)
        s_ah = after_entry["ask_h"].to_numpy(float)
        s_bc = after_entry["bid_c"].to_numpy(float)
        s_ac = after_entry["ask_c"].to_numpy(float)
        s_ts = after_entry["ts_utc"].to_numpy(np.int64)

        exit_idx = None
        exit_px = None
        exit_reason = None
        for j in range(len(after_entry)):
            if direction == "LONG":
                hit_sl = s_bl[j] <= sl_px
                hit_tp = s_ah[j] >= tp_px
            else:
                hit_sl = s_ah[j] >= sl_px
                hit_tp = s_bl[j] <= tp_px
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
            exit_idx = len(after_entry) - 1
            exit_px = float(s_bc[exit_idx] if direction == "LONG" else s_ac[exit_idx])
            exit_reason = "TIME"

        if direction == "LONG":
            pnl_r = (exit_px - entry_px) / risk
        else:
            pnl_r = (entry_px - exit_px) / risk

        trades.append({
            "symbol": symbol, "date": date, "direction": direction,
            "gap_pct": gap_pct, "prior_close": prior_close, "today_open": today_open,
            "entry_ts_ns": entry_ts, "entry_px": entry_px,
            "pre_high": pre_high, "pre_low": pre_low,
            "sl_px": sl_px, "tp_px": tp_px,
            "exit_ts_ns": int(s_ts[exit_idx]), "exit_px": exit_px,
            "exit_reason": exit_reason, "risk": risk, "pnl_r": pnl_r,
        })

    return pd.DataFrame(trades), skipped_small


def main():
    results_root = Path("research/results")
    results_root.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    sym = "USATECHIDXUSD"
    print(f"[{time.strftime('%H:%M:%S')}] load {sym}...", flush=True)
    bars = read_bars(root=Path("data"), symbol=sym, partition="dev", dev_only=True)
    print(f"  {len(bars):,} bars", flush=True)

    ts = pd.to_datetime(bars["ts_utc"], utc=True)
    years = (ts.max() - ts.min()).days / 365.25

    print(f"[{time.strftime('%H:%M:%S')}] scan gap fade v2 (CAUSAL SL from 09:30-09:34)...", flush=True)
    t_s = time.time()
    trades, skipped = run_one_symbol(sym, bars)
    print(f"  {len(trades)} trades in {time.time()-t_s:.1f}s  (skipped {skipped} small-gap days)", flush=True)

    trades.to_parquet(results_root / "gap_fade_v2_USATECHIDXUSD.parquet", index=False)

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
    print(f"GAP FADE v2 (CAUSAL) — RESULTS ({sym})")
    print("=" * 72)
    print(f"  trades: {len(trades)}")
    print(f"  win rate: {(trades.pnl_r > 0).mean()*100:.1f}%")
    print(f"  profit factor: {pf:.2f}")
    print(f"  mean R: {trades.pnl_r.mean():+.3f}")
    print(f"  sum R: {trades.pnl_r.sum():+.2f}")
    print(f"  max DD (R): {max_dd:.2f}")
    print(f"  trades/year: {len(trades)/years:.1f}")
    print(f"  trades/month: {len(trades)/years/12:.2f}")
    print(f"  directions: {trades['direction'].value_counts().to_dict()}")
    print(f"  exits: {trades['exit_reason'].value_counts().to_dict()}")
    print("-" * 72)
    annualized_r = len(trades) / years * trades.pnl_r.mean()
    print(f"  Annualized R: {annualized_r:+.2f}")
    print(f"  @ 0.5% risk on $10k: ${annualized_r*50:+.0f}/year")
    print(f"  @ 0.25% risk:       ${annualized_r*25:+.0f}/year")
    print("-" * 72)
    pf_ok = pf >= 1.3
    count_ok = (len(trades) / years) >= 30
    if pf_ok and count_ok:
        print(f"DECISION: GREEN — PF {pf:.2f} >= 1.3 AND {len(trades)/years:.0f} trades/year >= 30")
    else:
        print(f"DECISION: RED — PF {pf:.2f} (need 1.3); trades/year {len(trades)/years:.1f} (need 30)")
    print("-" * 72)
    print(f"Wall clock: {time.time()-t0:.1f}s\n", flush=True)


if __name__ == "__main__":
    main()
