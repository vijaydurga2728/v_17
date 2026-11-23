"""VWAP mean-reversion probe — stacks published best-practices.

Core mechanic:
  1. Cumulative session VWAP from 09:30 ET.
  2. Rolling intra-session standard deviation of mid-price around VWAP.
  3. Bands at VWAP ± 2σ.
  4. Entry: price prints a bar whose bid_h ≥ VWAP + 2σ (SHORT), then next bar closes
     back inside (bid_c < VWAP + 2σ). Mirror for LONG below -2σ.
  5. SL: beyond the extreme (max of bar high / min of bar low) ± 0.3 × ATR_14.
  6. TP: session VWAP touch (adaptive — distance varies per trade).
  7. Max 1 open position at a time. Max 3 trades/day/direction. One trade per bar.
  8. Window: 10:00 ET → 15:30 ET (avoid first 30 min + last 30 min).
  9. Hard exit at 15:30 ET.

Filters stacked (published best practice):
  F1. ATR_14 at entry must be in the LOWER 70% percentile of prior-20-day ATR values
      (mean reversion works in chop regime, not high-vol trend days).
  F2. Signal bar must close back inside the band within 5 min of the extreme.
  F3. Daily trend NEUTRAL preferred — daily |close - SMA20| / ATR_D < 1.5 (not in strong trend).

Report: trade count, WR, PF, mean R, sum R, max DD, trades/year, exits.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from v17.data.parquet_store import read_bars


ATR_PERIOD = 14
VWAP_START_ET = "09:30"
ENTRY_WINDOW_START_ET = "10:00"
ENTRY_WINDOW_END_ET = "15:30"
HARD_EXIT_ET = "15:45"
BAND_SIGMA = 2.0
CLOSE_BACK_WINDOW_MIN = 5
SL_ATR_MULT = 0.3
MAX_TRADES_PER_DIR_PER_DAY = 3
ATR_PERCENTILE_CAP = 0.70   # only trade if ATR in lower 70% of prior-20d ATR
SMA_PERIOD = 20


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


def _daily_atr_percentile(df: pd.DataFrame) -> dict:
    """For each date, compute the 20-day rolling percentile of daily ATR_14.

    Returns dict[date] -> (atr_d, percentile_in_20d_window).
    """
    ts_ny = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df2 = df.copy()
    df2["_date"] = ts_ny.dt.date
    daily = df2.groupby("_date").agg(
        h=("bid_h", "max"),
        l=("bid_l", "min"),
        c=("bid_c", "last"),
    ).sort_index()
    daily["pc"] = daily["c"].shift(1)
    daily["tr"] = np.maximum.reduce([
        (daily["h"] - daily["l"]).to_numpy(),
        (daily["h"] - daily["pc"]).abs().to_numpy(),
        (daily["l"] - daily["pc"]).abs().to_numpy(),
    ])
    daily["atr14_d"] = daily["tr"].rolling(14, min_periods=14).mean()
    # 20-day percentile rank of daily ATR
    def _pct(x):
        if len(x) < 2:
            return np.nan
        last = x[-1]
        return (x <= last).sum() / len(x)
    daily["atr_pct"] = daily["atr14_d"].rolling(20, min_periods=20).apply(_pct, raw=True)
    out = daily[["atr_pct"]].to_dict()["atr_pct"]
    return out


def _daily_trend_norm(df: pd.DataFrame) -> dict:
    """For each date, compute |prior_close - prior_SMA20| / prior_ATR14 — distance from trend."""
    ts_ny = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df2 = df.copy()
    df2["_date"] = ts_ny.dt.date
    daily = df2.groupby("_date").agg(
        h=("bid_h", "max"),
        l=("bid_l", "min"),
        c=("bid_c", "last"),
    ).sort_index()
    daily["pc"] = daily["c"].shift(1)
    tr = np.maximum.reduce([
        (daily["h"] - daily["l"]).to_numpy(),
        (daily["h"] - daily["pc"]).abs().to_numpy(),
        (daily["l"] - daily["pc"]).abs().to_numpy(),
    ])
    daily["atr14_d"] = pd.Series(tr, index=daily.index).rolling(14, min_periods=14).mean()
    daily["sma20_d"] = daily["c"].rolling(SMA_PERIOD, min_periods=SMA_PERIOD).mean()
    prior_c = daily["c"].shift(1)
    prior_sma = daily["sma20_d"].shift(1)
    prior_atr = daily["atr14_d"].shift(1)
    daily["trend_norm"] = (prior_c - prior_sma).abs() / prior_atr
    return daily["trend_norm"].to_dict()


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
    atr_pct_by_date = _daily_atr_percentile(df)
    trend_norm_by_date = _daily_trend_norm(df)

    trades = []
    f_vol_skip = 0
    f_trend_skip = 0

    for date, grp in df.groupby("_date", sort=True):
        atr_pct = atr_pct_by_date.get(date, np.nan)
        trend_norm = trend_norm_by_date.get(date, np.nan)

        # Filter F1: skip if ATR percentile too high (trending day)
        if np.isfinite(atr_pct) and atr_pct > ATR_PERCENTILE_CAP:
            f_vol_skip += 1
            continue
        # Filter F3: skip if strong daily trend
        if np.isfinite(trend_norm) and trend_norm >= 1.5:
            f_trend_skip += 1
            continue

        grp = grp.sort_values("ts_utc").reset_index(drop=True)
        hhmm = grp["_hhmm"].to_numpy()

        # Session bars (09:30 → end of day). Build VWAP + rolling std.
        sess_mask = hhmm >= VWAP_START_ET
        sess = grp[sess_mask].reset_index(drop=True)
        if len(sess) < 60:
            continue

        sess_bc = sess["bid_c"].to_numpy(float)
        sess_ac = sess["ask_c"].to_numpy(float)
        sess_bh = sess["bid_h"].to_numpy(float)
        sess_bl = sess["bid_l"].to_numpy(float)
        sess_ah = sess["ask_h"].to_numpy(float)
        sess_al = sess["ask_l"].to_numpy(float)
        sess_bv = sess["bid_volume"].to_numpy(float)
        sess_av = sess["ask_volume"].to_numpy(float)
        sess_mid = (sess_bc + sess_ac) / 2.0
        sess_vol = np.where(sess_bv + sess_av > 0, sess_bv + sess_av, 1e-9)
        sess_ts = sess["ts_utc"].to_numpy(np.int64)
        sess_hhmm = sess["_hhmm"].to_numpy()
        # Map sess index back to full-df index for ATR lookup
        sess_full_idx = grp[sess_mask].index.to_numpy()

        vwap = np.cumsum(sess_mid * sess_vol) / np.cumsum(sess_vol)
        # Rolling std of (mid - vwap) over 30-bar window (approx 30 min)
        dev = sess_mid - vwap
        dev_series = pd.Series(dev)
        sig = dev_series.rolling(30, min_periods=30).std().to_numpy()

        upper = vwap + BAND_SIGMA * sig
        lower = vwap - BAND_SIGMA * sig

        # Track trades per direction per day
        n_long = 0
        n_short = 0
        i = 0
        while i < len(sess) - 1:
            if not (ENTRY_WINDOW_START_ET <= sess_hhmm[i] < ENTRY_WINDOW_END_ET):
                i += 1
                continue
            if not np.isfinite(upper[i]) or not np.isfinite(lower[i]):
                i += 1
                continue

            direction = None
            extreme_price = None
            extreme_idx = None

            # SHORT: high pokes above upper band
            if sess_bh[i] >= upper[i] and n_short < MAX_TRADES_PER_DIR_PER_DAY:
                # Look for close-back-inside within 5 bars
                for j in range(i + 1, min(i + CLOSE_BACK_WINDOW_MIN + 1, len(sess))):
                    if sess_bc[j] < upper[j]:
                        direction = "SHORT"
                        extreme_price = max(sess_bh[k] for k in range(i, j + 1))
                        extreme_idx = j
                        break
            # LONG: low pokes below lower band
            elif sess_bl[i] <= lower[i] and n_long < MAX_TRADES_PER_DIR_PER_DAY:
                for j in range(i + 1, min(i + CLOSE_BACK_WINDOW_MIN + 1, len(sess))):
                    if sess_bc[j] > lower[j]:
                        direction = "LONG"
                        extreme_price = min(sess_bl[k] for k in range(i, j + 1))
                        extreme_idx = j
                        break

            if direction is None:
                i += 1
                continue

            entry_idx = extreme_idx
            atr_entry = float(atr_full[int(sess_full_idx[entry_idx])])
            if not np.isfinite(atr_entry) or atr_entry <= 0:
                i += 1
                continue

            if direction == "LONG":
                entry_px = float(sess_ac[entry_idx])
                sl_px = extreme_price - SL_ATR_MULT * atr_entry
                risk = entry_px - sl_px
                if risk <= 0:
                    i += 1
                    continue
                tp_px = float(vwap[entry_idx])  # VWAP touch
                # Must be above entry for LONG to be meaningful
                if tp_px <= entry_px:
                    i += 1
                    continue
                n_long += 1
            else:
                entry_px = float(sess_bc[entry_idx])
                sl_px = extreme_price + SL_ATR_MULT * atr_entry
                risk = sl_px - entry_px
                if risk <= 0:
                    i += 1
                    continue
                tp_px = float(vwap[entry_idx])
                if tp_px >= entry_px:
                    i += 1
                    continue
                n_short += 1

            # Walk forward to SL / TP / hard exit
            exit_idx = None
            exit_px = None
            exit_reason = None
            for j in range(entry_idx + 1, len(sess)):
                if sess_hhmm[j] >= HARD_EXIT_ET:
                    exit_idx = j
                    exit_px = float(sess_bc[j] if direction == "LONG" else sess_ac[j])
                    exit_reason = "TIME"
                    break
                if direction == "LONG":
                    hit_sl = sess_bl[j] <= sl_px
                    hit_tp = sess_ah[j] >= tp_px
                else:
                    hit_sl = sess_ah[j] >= sl_px
                    hit_tp = sess_bl[j] <= tp_px
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
                exit_idx = len(sess) - 1
                exit_px = float(sess_bc[exit_idx] if direction == "LONG" else sess_ac[exit_idx])
                exit_reason = "EOD"

            if direction == "LONG":
                pnl_r = (exit_px - entry_px) / risk
            else:
                pnl_r = (entry_px - exit_px) / risk

            trades.append({
                "symbol": symbol, "date": date, "direction": direction,
                "entry_ts_ns": int(sess_ts[entry_idx]), "entry_px": entry_px,
                "sl_px": sl_px, "tp_px": tp_px,
                "exit_ts_ns": int(sess_ts[exit_idx]), "exit_px": exit_px,
                "exit_reason": exit_reason, "risk": risk, "pnl_r": pnl_r,
                "atr_pct": atr_pct, "trend_norm": trend_norm,
            })

            # Advance past exit so next iteration starts fresh
            i = exit_idx + 1

    return pd.DataFrame(trades), f_vol_skip, f_trend_skip


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

    print(f"[{time.strftime('%H:%M:%S')}] scan VWAP MR (2σ fade + chop + trend-neutral filters)...", flush=True)
    t_s = time.time()
    trades, vol_skip, trend_skip = run_one_symbol(sym, bars)
    print(f"  {len(trades)} trades in {time.time()-t_s:.1f}s  (skipped {vol_skip} vol / {trend_skip} trend days)", flush=True)

    trades.to_parquet(results_root / "vwap_mr_USATECHIDXUSD.parquet", index=False)

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
    print(f"VWAP MR — RESULTS ({sym})")
    print("=" * 72)
    print(f"  trades: {len(trades)}")
    print(f"  win rate: {(trades.pnl_r > 0).mean()*100:.1f}%")
    print(f"  profit factor: {pf:.2f}")
    print(f"  mean R: {trades.pnl_r.mean():+.3f}")
    print(f"  sum R: {trades.pnl_r.sum():+.2f}")
    print(f"  max DD (R): {max_dd:.2f}")
    print(f"  trades/year: {len(trades)/years:.1f}")
    print(f"  trades/month: {len(trades)/years/12:.1f}")
    print(f"  directions: {trades['direction'].value_counts().to_dict()}")
    print(f"  exits: {trades['exit_reason'].value_counts().to_dict()}")
    print("-" * 72)
    annualized_r = len(trades) / years * trades.pnl_r.mean()
    print(f"  Annualized R: {annualized_r:+.2f}")
    print(f"  @ 0.5% risk on $10k: ${annualized_r*50:+.0f}/year")
    print(f"  @ 1% risk:           ${annualized_r*100:+.0f}/year")
    print("-" * 72)
    pf_ok = pf >= 1.3
    count_ok = (len(trades) / years) >= 100
    if pf_ok and count_ok:
        print(f"DECISION: GREEN — PF {pf:.2f} >= 1.3 AND {len(trades)/years:.0f} trades/year >= 100")
    else:
        print(f"DECISION: RED — PF {pf:.2f} (need 1.3); trades/year {len(trades)/years:.1f} (need 100)")
    print("-" * 72)
    print(f"Wall clock: {time.time()-t0:.1f}s\n", flush=True)


if __name__ == "__main__":
    main()
