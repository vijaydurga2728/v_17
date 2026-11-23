"""ICT NY AM Silver Bullet — "No Daily Bias" variant with 09:00 H1 anchor.

Spec (from user-provided video extraction):
  - Reference: 09:00-09:59 NY H1 candle. Mark its high H and low L.
  - Session window: 10:00-11:00 NY (M1 scan).
  - Sweep: M1 bid_l < L (sets up LONG) OR bid_h > H (sets up SHORT).
  - Displacement + MSS: after sweep, wait for a strong M1 bar that closes
    back inside [L, H] (crosses structure). Body must be ≥ 60% of range
    AND range ≥ 1.2 × ATR_14 M1 (standard displacement filter).
  - FVG: 3-bar gap formed by the displacement bar k using (k-2, k-1, k).
    Bullish FVG when LONG: L_k > H_{k-2}. Bearish FVG when SHORT symmetric.
  - Entry: LIMIT at FVG CE (midpoint). Direction = MSS direction (fade
    the sweep). Cancel if unfilled by 11:00 NY.
  - SL: sweep extreme (no buffer).
  - TP: opposite side of 09:00 H1 candle (L for SHORT, H for LONG).
  - BE move: at +3R MFE, move SL to entry. Then hold to TP or BE stop.
  - Hard exit: 15:30 NY if neither hit (safety).
  - One trade per (symbol, day).
  - Risk: 1% equity (per spec, but we report in R units).

Symbols: EURUSD, GBPUSD (user's ingested data).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from v17.data.parquet_store import read_bars


ATR_PERIOD = 14
DISPLACEMENT_BODY_RATIO = 0.60
DISPLACEMENT_RANGE_ATR_MULT = 1.2
BE_TRIGGER_R = 3.0
REFERENCE_ET = "09:00"
WINDOW_START_ET = "10:00"
WINDOW_END_ET = "11:00"
HARD_EXIT_ET = "15:30"


def _atr14(h, l, c):
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return pd.Series(tr).rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean().to_numpy()


def _is_displacement(bar_o, bar_h, bar_l, bar_c, atr_v, direction):
    rng = bar_h - bar_l
    if rng <= 0:
        return False
    body = abs(bar_c - bar_o)
    if body / rng < DISPLACEMENT_BODY_RATIO:
        return False
    if rng < DISPLACEMENT_RANGE_ATR_MULT * atr_v:
        return False
    # Direction check: bullish body for LONG setup, bearish for SHORT
    if direction == "LONG" and bar_c <= bar_o:
        return False
    if direction == "SHORT" and bar_c >= bar_o:
        return False
    return True


def run_one_symbol(sym: str, m1: pd.DataFrame) -> pd.DataFrame:
    df = m1.copy()
    df["_ts_ny"] = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df["_date"] = df["_ts_ny"].dt.date
    df["_hhmm"] = df["_ts_ny"].dt.strftime("%H:%M")

    bh = df["bid_h"].to_numpy(float)
    bl = df["bid_l"].to_numpy(float)
    bc = df["bid_c"].to_numpy(float)
    bo = df["bid_o"].to_numpy(float)
    ah = df["ask_h"].to_numpy(float)
    al = df["ask_l"].to_numpy(float)
    ac = df["ask_c"].to_numpy(float)
    ao = df["ask_o"].to_numpy(float)
    atr = _atr14(bh, bl, bc)

    trades = []

    for date, grp in df.groupby("_date", sort=True):
        grp = grp.sort_values("ts_utc").reset_index(drop=True)
        hhmm = grp["_hhmm"].to_numpy()
        orig_idx = grp.index.to_numpy()

        # Reference 09:00 NY H1 candle: bars 09:00-09:59 NY
        ref_mask = (hhmm >= REFERENCE_ET) & (hhmm < WINDOW_START_ET)
        ref = grp[ref_mask]
        if len(ref) < 30:
            continue
        H = float(ref["bid_h"].max())
        L = float(ref["bid_l"].min())

        # Scan window 10:00-11:00 NY on M1
        win_mask = (hhmm >= WINDOW_START_ET) & (hhmm < WINDOW_END_ET)
        win = grp[win_mask].reset_index(drop=True)
        if win.empty:
            continue

        w_bh = win["bid_h"].to_numpy(float)
        w_bl = win["bid_l"].to_numpy(float)
        w_bc = win["bid_c"].to_numpy(float)
        w_bo = win["bid_o"].to_numpy(float)
        w_ah = win["ask_h"].to_numpy(float)
        w_ac = win["ask_c"].to_numpy(float)
        w_ao = win["ask_o"].to_numpy(float)
        w_ts = win["ts_utc"].to_numpy(np.int64)
        w_full = grp[win_mask].index.to_numpy()  # positional idx in grp

        # Also keep entire day post-11:00 for walk-forward on SL/TP/BE
        after_mask = hhmm >= WINDOW_END_ET
        after = grp[after_mask | win_mask].reset_index(drop=True)
        # We will iterate all post-window bars using grp's original arrays directly via orig_idx
        # Build day-full numpy arrays
        day_bh = grp["bid_h"].to_numpy(float)
        day_bl = grp["bid_l"].to_numpy(float)
        day_bc = grp["bid_c"].to_numpy(float)
        day_ah = grp["ask_h"].to_numpy(float)
        day_ac = grp["ask_c"].to_numpy(float)
        day_ts = grp["ts_utc"].to_numpy(np.int64)
        day_hhmm = hhmm

        # Detect FIRST sweep then displacement+MSS in window
        swept_extreme = None
        direction = None
        sweep_bar_win_idx = None
        for j in range(len(win)):
            if swept_extreme is None:
                if w_bl[j] < L:
                    swept_extreme = float(w_bl[j])
                    direction = "LONG"
                    sweep_bar_win_idx = j
                    # keep updating swept_extreme on subsequent bars that go lower
                elif w_bh[j] > H:
                    swept_extreme = float(w_bh[j])
                    direction = "SHORT"
                    sweep_bar_win_idx = j
            else:
                # Update extreme if sweep continues
                if direction == "LONG" and w_bl[j] < swept_extreme:
                    swept_extreme = float(w_bl[j])
                    sweep_bar_win_idx = j
                elif direction == "SHORT" and w_bh[j] > swept_extreme:
                    swept_extreme = float(w_bh[j])
                    sweep_bar_win_idx = j

        if direction is None:
            continue

        # After sweep, look for displacement bar that closes back inside [L, H]
        mss_idx = None
        fvg = None  # dict: top, bottom, ce
        for j in range(sweep_bar_win_idx + 1, len(win)):
            orig_j = int(w_full[j])
            atr_v = float(atr[orig_j])
            if not np.isfinite(atr_v) or atr_v <= 0:
                continue
            # Check displacement direction matches MSS (reverse of sweep direction)
            disp_dir = direction  # LONG = bullish displacement, SHORT = bearish
            if not _is_displacement(w_bo[j], w_bh[j], w_bl[j], w_bc[j], atr_v, disp_dir):
                continue
            # MSS: close back inside [L, H]
            if direction == "LONG":
                if w_bc[j] <= L:
                    continue
                # Found bullish displacement + close above L
                # Check for FVG at (orig_j-2, orig_j-1, orig_j)
                if orig_j < 2:
                    continue
                g_bot = float(bh[orig_j - 2])
                g_top = float(bl[orig_j])
                if g_top > g_bot:
                    fvg = {"bottom": g_bot, "top": g_top, "ce": (g_top + g_bot) / 2.0}
                    mss_idx = j
                    break
            else:
                if w_bc[j] >= H:
                    continue
                if orig_j < 2:
                    continue
                g_top = float(bl[orig_j - 2])
                g_bot = float(bh[orig_j])
                if g_top > g_bot:
                    fvg = {"bottom": g_bot, "top": g_top, "ce": (g_top + g_bot) / 2.0}
                    mss_idx = j
                    break

        if fvg is None:
            continue

        # Place limit order at CE. Fire if any M1 bar from MSS+1 .. window-end touches CE.
        entry_idx = None
        entry_px = None
        for j in range(mss_idx + 1, len(win)):
            if direction == "LONG":
                if w_bl[j] <= fvg["ce"] <= w_bh[j]:
                    entry_idx = j
                    entry_px = float(fvg["ce"])  # limit fill at CE (approx: use bid side for LONG entry at ask, simplify)
                    # LONG entry = buy at ask; approximate CE+spread via ask price at that bar
                    entry_px = max(entry_px, float(w_ac[j]))  # pessimistic — ask may be higher
                    break
            else:
                if w_bl[j] <= fvg["ce"] <= w_bh[j]:
                    entry_idx = j
                    entry_px = min(float(fvg["ce"]), float(w_bc[j]))
                    break

        if entry_idx is None:
            continue

        # SL = sweep extreme (no buffer per spec)
        sl_px = swept_extreme
        if direction == "LONG":
            risk = entry_px - sl_px
            if risk <= 0:
                continue
            tp_px = H  # opposite side of 09:00 candle
            if tp_px <= entry_px:
                continue
        else:
            risk = sl_px - entry_px
            if risk <= 0:
                continue
            tp_px = L
            if tp_px >= entry_px:
                continue

        # BE trigger price
        if direction == "LONG":
            be_trigger = entry_px + BE_TRIGGER_R * risk
        else:
            be_trigger = entry_px - BE_TRIGGER_R * risk

        # Walk forward using day-full arrays from grp
        entry_grp_idx = int(w_full[entry_idx])
        # Find exit scanning bars: from entry_grp_idx+1 until hhmm >= HARD_EXIT_ET
        exit_idx = None
        exit_px = None
        exit_reason = None
        current_sl = sl_px
        trailed = False
        for k in range(entry_grp_idx + 1, len(grp)):
            if day_hhmm[k] >= HARD_EXIT_ET:
                exit_idx = k
                exit_px = float(day_bc[k] if direction == "LONG" else day_ac[k])
                exit_reason = "TIME"
                break
            # BE move
            if not trailed:
                if direction == "LONG" and day_bh[k] >= be_trigger:
                    current_sl = entry_px
                    trailed = True
                elif direction == "SHORT" and day_bl[k] <= be_trigger:
                    current_sl = entry_px
                    trailed = True
            if direction == "LONG":
                hit_sl = day_bl[k] <= current_sl
                hit_tp = day_ah[k] >= tp_px
            else:
                hit_sl = day_ah[k] >= current_sl
                hit_tp = day_bl[k] <= tp_px
            if hit_sl and hit_tp:
                exit_idx, exit_px, exit_reason = k, current_sl, ("BE" if trailed else "SL")
                break
            if hit_sl:
                exit_idx, exit_px, exit_reason = k, current_sl, ("BE" if trailed else "SL")
                break
            if hit_tp:
                exit_idx, exit_px, exit_reason = k, tp_px, "TP"
                break

        if exit_idx is None:
            exit_idx = len(grp) - 1
            exit_px = float(day_bc[exit_idx] if direction == "LONG" else day_ac[exit_idx])
            exit_reason = "EOD"

        pnl_r = ((exit_px - entry_px) / risk) if direction == "LONG" else ((entry_px - exit_px) / risk)
        trades.append({
            "symbol": sym, "date": date, "direction": direction,
            "ref_high": H, "ref_low": L, "swept_extreme": swept_extreme,
            "fvg_ce": fvg["ce"], "fvg_top": fvg["top"], "fvg_bottom": fvg["bottom"],
            "entry_ts_ns": int(w_ts[entry_idx]), "entry_px": entry_px,
            "sl_px_initial": sl_px, "tp_px": tp_px, "risk": risk, "be_trigger_px": be_trigger,
            "exit_ts_ns": int(day_ts[exit_idx]), "exit_px": exit_px,
            "exit_reason": exit_reason, "trailed_to_be": trailed,
            "pnl_r": pnl_r,
        })

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
    print(f"  trades: {n}  ({n/years:.1f}/year, {n/years/12:.2f}/month)")
    print(f"  WR: {(df.pnl_r > 0).mean()*100:.1f}%")
    print(f"  PF: {pf:.2f}")
    print(f"  mean R: {df.pnl_r.mean():+.3f}")
    print(f"  sum R: {df.pnl_r.sum():+.2f}")
    print(f"  max DD (R): {max_dd:.2f}")
    print(f"  exits: {df['exit_reason'].value_counts().to_dict()}")
    print(f"  trailed to BE: {int(df['trailed_to_be'].sum())}/{n}")
    print(f"  directions: {df['direction'].value_counts().to_dict()}")
    ann_r = (n / years) * df.pnl_r.mean()
    print(f"  Annualized R: {ann_r:+.2f}  → @0.5% risk on $10k: ${ann_r*50:+.0f}/year  @1%: ${ann_r*100:+.0f}")


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

        print(f"[{time.strftime('%H:%M:%S')}] scan {sym}...", flush=True)
        t_s = time.time()
        trades = run_one_symbol(sym, m1)
        print(f"  {len(trades)} trades in {time.time()-t_s:.1f}s", flush=True)
        trades.to_parquet(results_root / f"sb_h1anchor_{sym}.parquet", index=False)
        _summarize(f"{sym} SB-H1anchor (video spec)", trades, years)
        all_rows.append(trades)

    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        total_years = 10.0 * 2
        _summarize("COMBINED", combined, total_years)

    print(f"\nWall clock: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
