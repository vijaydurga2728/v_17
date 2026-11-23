"""D1 Ensemble probe — hedge-fund-grade methodology.

Builds a 3-signal daily ensemble across 3 symbols (EURUSD, GBPUSD, USATECHIDXUSD).

Signals (each computed daily, with 1-day shift for causality):
  S1. Time-series momentum: sign(log-return over 252 trading days).
  S2. Mean-reversion: -sign(zscore of 20d return) when |z| > 1.5, else 0.
  S3. Vol-breakout: sign(5d return) when ATR_20 / ATR_60 > 1.1, else 0.

Position sizing (hedge-fund style):
  - Target annualized vol = 15% per symbol.
  - Weight = signal * (target_vol / rolling_20d_vol).
  - Cap per-symbol gross weight at 2.0x to avoid blowups.
  - Combine 3 signals per symbol by averaging weights.

Portfolio = equal-weighted sum across 3 symbols. Rebalance daily. No costs
assumed in this probe (fair comparison to CTA literature). Costs would reduce
Sharpe by ~0.1-0.2 on daily rebalancing — significant but not determinative.

Report:
  - Per-signal Sharpe
  - Per-symbol combined Sharpe
  - Portfolio Sharpe (ensemble)
  - Annualized return + vol
  - Max drawdown
  - 30-day return percentiles (relevant for FTMO challenge window)

Decision gate:
  GREEN if portfolio Sharpe >= 0.8 AND max DD < 25% (annualized vol scale).
  AMBER if 0.5 <= Sharpe < 0.8.
  RED if Sharpe < 0.5.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from v17.data.parquet_store import read_bars


TARGET_VOL_ANNUAL = 0.15
MAX_LEVERAGE_PER_SIGNAL = 2.0
MOM_LOOKBACK = 252
MR_LOOKBACK = 20
MR_Z_THRESHOLD = 1.5
VB_SHORT = 5
VB_ATR_SHORT = 20
VB_ATR_LONG = 60
VB_ATR_RATIO = 1.1
VOL_LOOKBACK = 20
TRADING_DAYS = 252


def _resample_d1(bars: pd.DataFrame) -> pd.DataFrame:
    """Resample M1 bars → D1 using last bar of NY session per date."""
    ts = pd.to_datetime(bars["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df = bars.copy()
    df["_date"] = ts.dt.date
    agg = df.groupby("_date").agg(
        open=("bid_o", "first"),
        high=("bid_h", "max"),
        low=("bid_l", "min"),
        close=("bid_c", "last"),
    ).sort_index()
    return agg


def _signals(d1: pd.DataFrame) -> pd.DataFrame:
    """Compute 3 signals per daily bar. Shift by 1 for causality."""
    c = d1["close"]
    h = d1["high"]
    l = d1["low"]
    prev_c = c.shift(1)
    log_ret_1d = np.log(c / prev_c)

    # TS momentum: sign of log return over MOM_LOOKBACK days
    mom_ret = np.log(c / c.shift(MOM_LOOKBACK))
    s1 = np.sign(mom_ret)

    # Mean-reversion: 20d z-score; signal only when |z| > threshold
    ret_20 = np.log(c / c.shift(MR_LOOKBACK))
    rolling_mean = ret_20.rolling(60, min_periods=60).mean()
    rolling_std = ret_20.rolling(60, min_periods=60).std()
    zscore = (ret_20 - rolling_mean) / rolling_std
    s2 = -np.sign(zscore).where(zscore.abs() > MR_Z_THRESHOLD, 0.0)

    # Vol-breakout: direction = sign of 5d return; gate by ATR regime
    tr = pd.concat([
        (h - l),
        (h - prev_c).abs(),
        (l - prev_c).abs(),
    ], axis=1).max(axis=1)
    atr_short = tr.rolling(VB_ATR_SHORT, min_periods=VB_ATR_SHORT).mean()
    atr_long = tr.rolling(VB_ATR_LONG, min_periods=VB_ATR_LONG).mean()
    atr_ratio = atr_short / atr_long
    ret_5 = np.log(c / c.shift(VB_SHORT))
    s3 = np.sign(ret_5).where(atr_ratio > VB_ATR_RATIO, 0.0)

    # Shift all signals by 1 day (apply tomorrow's position from today's close signal)
    out = pd.DataFrame({
        "log_ret_1d": log_ret_1d,
        "s1_mom": s1.shift(1),
        "s2_mr": s2.shift(1),
        "s3_vb": s3.shift(1),
    })
    return out


def _vol_target_weight(signal: pd.Series, log_ret: pd.Series) -> pd.Series:
    """Weight = signal * (target_vol / realized_vol), capped at MAX_LEVERAGE."""
    realized_vol_annual = log_ret.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).std() * np.sqrt(TRADING_DAYS)
    scale = (TARGET_VOL_ANNUAL / realized_vol_annual).clip(upper=MAX_LEVERAGE_PER_SIGNAL)
    return (signal * scale).fillna(0.0)


def _summarize_series(name: str, daily_ret: pd.Series) -> dict:
    daily_ret = daily_ret.dropna()
    if len(daily_ret) == 0:
        return {"name": name, "sharpe": 0.0, "ann_ret": 0.0, "ann_vol": 0.0, "max_dd": 0.0}
    mean_d = daily_ret.mean()
    std_d = daily_ret.std(ddof=1)
    sharpe = (mean_d / std_d) * np.sqrt(TRADING_DAYS) if std_d > 0 else 0.0
    ann_ret = mean_d * TRADING_DAYS
    ann_vol = std_d * np.sqrt(TRADING_DAYS)
    equity = (1 + daily_ret).cumprod()
    peak = equity.cummax()
    dd = (peak - equity) / peak
    max_dd = dd.max()

    # 30-day rolling return percentiles (for FTMO relevance)
    roll_30 = (1 + daily_ret).rolling(30, min_periods=30).apply(np.prod, raw=True) - 1
    p_10pct_month = (roll_30 >= 0.10).mean()

    return {
        "name": name,
        "sharpe": float(sharpe),
        "ann_ret": float(ann_ret),
        "ann_vol": float(ann_vol),
        "max_dd": float(max_dd),
        "n_days": int(len(daily_ret)),
        "p_month_ge_10pct": float(p_10pct_month),
    }


def main() -> None:
    results_root = Path("research/results")
    results_root.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    symbols = ["EURUSD", "GBPUSD", "USATECHIDXUSD"]
    per_sym_data = {}
    for sym in symbols:
        print(f"[{time.strftime('%H:%M:%S')}] load {sym} dev bars...", flush=True)
        bars = read_bars(root=Path("data"), symbol=sym, partition="dev", dev_only=True)
        print(f"  {len(bars):,} M1 bars", flush=True)
        d1 = _resample_d1(bars)
        print(f"  {len(d1)} D1 bars", flush=True)
        sig = _signals(d1)
        # Compute weights per signal using vol-targeting
        w1 = _vol_target_weight(sig["s1_mom"], sig["log_ret_1d"])
        w2 = _vol_target_weight(sig["s2_mr"], sig["log_ret_1d"])
        w3 = _vol_target_weight(sig["s3_vb"], sig["log_ret_1d"])
        # Combined weight = mean of 3 signal weights
        w_combined = (w1 + w2 + w3) / 3.0

        # Daily pnl per signal and combined
        pnl_s1 = w1 * sig["log_ret_1d"]
        pnl_s2 = w2 * sig["log_ret_1d"]
        pnl_s3 = w3 * sig["log_ret_1d"]
        pnl_c = w_combined * sig["log_ret_1d"]

        per_sym_data[sym] = {
            "pnl_s1": pnl_s1, "pnl_s2": pnl_s2, "pnl_s3": pnl_s3, "pnl_c": pnl_c,
        }

    # Per-signal aggregate across symbols (mean daily pnl)
    s1_agg = sum(per_sym_data[s]["pnl_s1"].fillna(0.0) for s in symbols) / len(symbols)
    s2_agg = sum(per_sym_data[s]["pnl_s2"].fillna(0.0) for s in symbols) / len(symbols)
    s3_agg = sum(per_sym_data[s]["pnl_s3"].fillna(0.0) for s in symbols) / len(symbols)

    # Portfolio = mean of 3 symbols' combined pnl
    port_pnl = sum(per_sym_data[s]["pnl_c"].fillna(0.0) for s in symbols) / len(symbols)

    rows = []
    rows.append(_summarize_series("Signal 1 (TS momentum)", s1_agg))
    rows.append(_summarize_series("Signal 2 (Mean reversion)", s2_agg))
    rows.append(_summarize_series("Signal 3 (Vol breakout)", s3_agg))
    for sym in symbols:
        rows.append(_summarize_series(f"{sym} combined", per_sym_data[sym]["pnl_c"]))
    rows.append(_summarize_series("PORTFOLIO (ensemble)", port_pnl))

    # Save combined summary
    summary_df = pd.DataFrame(rows)
    summary_df.to_parquet(results_root / "d1_ensemble_summary.parquet", index=False)

    print("\n" + "=" * 76)
    print("D1 ENSEMBLE — RESULTS (3 symbols × 3 signals, vol-targeted)")
    print("=" * 76)
    for r in rows:
        print(f"\n{r['name']}")
        print(f"  Sharpe: {r['sharpe']:+.2f}")
        print(f"  Annual return: {r['ann_ret']*100:+.1f}%")
        print(f"  Annual vol: {r['ann_vol']*100:.1f}%")
        print(f"  Max DD: {r['max_dd']*100:.1f}%")
        print(f"  P(30-day return >= 10%): {r['p_month_ge_10pct']*100:.1f}%")
    print("\n" + "-" * 76)

    port_sharpe = rows[-1]["sharpe"]
    port_dd = rows[-1]["max_dd"]
    port_p10 = rows[-1]["p_month_ge_10pct"]
    if port_sharpe >= 0.8 and port_dd < 0.25:
        decision = f"GREEN — portfolio Sharpe {port_sharpe:.2f} >= 0.8 AND max DD {port_dd*100:.0f}% < 25%"
    elif port_sharpe >= 0.5:
        decision = f"AMBER — portfolio Sharpe {port_sharpe:.2f} in [0.5, 0.8); needs ensemble expansion"
    else:
        decision = f"RED — portfolio Sharpe {port_sharpe:.2f} < 0.5"
    print(f"DECISION: {decision}")
    print(f"P(30-day win >= 10%) = {port_p10*100:.1f}%  ← FTMO challenge win probability per month")
    print("-" * 76)
    print(f"Wall clock: {time.time()-t0:.1f}s\n", flush=True)


if __name__ == "__main__":
    main()
