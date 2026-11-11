"""Pooled FX scheme-1 — symmetric RSI(2) on 8 FX pairs, Fisher-combined p-values.

For each FX pair:
  1. Run symmetric RSI(2) long(RSI<10) + short(RSI>90) with SMA(5) exit, no TIME_CAP.
  2. Run scheme-1 MCPT (mean_r test statistic, 500 permutations).
  3. Record per-pair p_mean_r for dev and holdout.
Then combine via Fisher's method: chi2 = -2 * sum(log p_i), df = 2k.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.engine_runner import _to_mid_bars
from v17.backtest.walkforward import Fold, generate_folds
from v17.data.parquet_store import read_bars_d1
from v17.validation.seeds import permutation_seed


N_PERMUTATIONS = 500
ALPHA = 0.05

FX_PAIRS = [
    ("EURUSD",  0.00005),
    ("GBPUSD",  0.00005),
    ("AUDUSD",  0.00005),
    ("NZDUSD",  0.00005),
    ("USDCAD",  0.00005),
    ("USDCHF",  0.00005),
    ("USDJPY",  0.005),     # JPY quoted in 3 decimals; 0.5 pips = 0.005
    ("EURGBP",  0.00005),
]


@dataclass(frozen=True)
class Cfg:
    engine_id: str
    symbol: str
    priority_order: int


def _rsi_wilder(close, period):
    n = len(close); rsi = np.full(n, np.nan)
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0); loss = np.where(delta < 0, -delta, 0)
    ag = gain[1:period + 1].mean(); al = loss[1:period + 1].mean()
    for i in range(period, n):
        if i > period:
            ag = (ag * (period - 1) + gain[i]) / period
            al = (al * (period - 1) + loss[i]) / period
        if al == 0 and ag == 0:
            rsi[i] = 50
        elif al == 0:
            rsi[i] = 100
        else:
            rsi[i] = 100 - 100 / (1 + ag / al)
    return rsi


def _sma(x, p):
    n = len(x); out = np.full(n, np.nan)
    cum = np.cumsum(x); out[p - 1] = cum[p - 1] / p
    for i in range(p, n):
        out[i] = (cum[i] - cum[i - p]) / p
    return out


def _sim_trade(entry_idx, side, open_, close, sma5, ts, slip, n, time_cap=60):
    actual_entry = entry_idx + 1
    if actual_entry >= n:
        return None
    if side == "long":
        entry_price = open_[actual_entry] + slip
    else:
        entry_price = open_[actual_entry] - slip
    r_dist = max(close[entry_idx] * 0.01, 1e-9)
    exit_px = None
    for j in range(actual_entry, min(actual_entry + time_cap + 1, n)):
        if side == "long" and np.isfinite(sma5[j]) and close[j] > sma5[j]:
            exit_px = close[j]; break
        if side == "short" and np.isfinite(sma5[j]) and close[j] < sma5[j]:
            exit_px = close[j]; break
    if exit_px is None:
        exit_px = close[min(actual_entry + time_cap, n - 1)]
    if side == "long":
        pnl = exit_px - entry_price
    else:
        pnl = entry_price - exit_px
    return pnl / r_dist


def _collect_trades(bars, slip, fold):
    mid = _to_mid_bars(bars).sort_values("ts_ns").reset_index(drop=True)
    ts = mid["ts_ns"].to_numpy()
    close = mid["close"].to_numpy(); open_ = mid["open"].to_numpy()
    rsi = _rsi_wilder(close, 2); sma5 = _sma(close, 5)
    trades = []; n = len(mid); i = 5
    while i < n - 1:
        if ts[i] < fold.oos_start: i += 1; continue
        if ts[i] >= fold.oos_end: break
        if not np.isfinite(rsi[i]): i += 1; continue
        side = None
        if rsi[i] < 10: side = "long"
        elif rsi[i] > 90: side = "short"
        if side is None: i += 1; continue
        pnl_r = _sim_trade(i, side, open_, close, sma5, ts, slip, n)
        if pnl_r is not None and np.isfinite(pnl_r):
            trades.append({"ts_entry_ns": int(ts[i]), "side": side, "pnl_r": pnl_r})
        # advance past exit
        actual_entry = i + 1
        next_i = actual_entry
        for k in range(actual_entry, min(actual_entry + 61, n)):
            if side == "long" and np.isfinite(sma5[k]) and close[k] > sma5[k]:
                next_i = k; break
            if side == "short" and np.isfinite(sma5[k]) and close[k] < sma5[k]:
                next_i = k; break
        i = next_i + 1
    return pd.DataFrame(trades)


def _run_pair_scheme1(sym, slip, bars, trades_df, ws, we, engine_id, label):
    if trades_df.empty:
        return None
    mid = _to_mid_bars(bars).sort_values("ts_ns").reset_index(drop=True)
    ts = mid["ts_ns"].to_numpy()
    close = mid["close"].to_numpy(); open_ = mid["open"].to_numpy()
    sma5 = _sma(close, 5)
    n = len(mid)
    in_window = (ts >= ws) & (ts < we)
    eligible = np.where(in_window)[0]
    eligible = eligible[(eligible >= 5) & (eligible < n - 2)]

    n_obs = len(trades_df)
    if n_obs > len(eligible):
        return None
    obs_mean = float(trades_df["pnl_r"].mean())

    null_means = np.full(N_PERMUTATIONS, np.nan)
    for p in range(N_PERMUTATIONS):
        seed = permutation_seed(engine_id, f"sym_pool_{label}", p)
        rng = np.random.default_rng(seed)
        sampled = rng.choice(eligible, size=n_obs, replace=False)
        sides = rng.choice(["long", "short"], size=n_obs)
        pnls = []
        for ei, s in zip(sampled, sides):
            r = _sim_trade(int(ei), s, open_, close, sma5, ts, slip, n)
            if r is not None and np.isfinite(r):
                pnls.append(r)
        if pnls:
            null_means[p] = np.mean(pnls)
    finite = null_means[np.isfinite(null_means)]
    p_mean = float((finite >= obs_mean).mean()) if len(finite) else float("nan")
    return {
        "symbol": sym,
        "n_trades": n_obs,
        "obs_mean_r": obs_mean,
        "null_mean_median": float(np.nanmedian(null_means)),
        "p_mean_r": p_mean,
    }


def fisher_combine(pvals):
    valid = [max(p, 1e-10) for p in pvals if p is not None and np.isfinite(p)]
    k = len(valid)
    if k == 0:
        return float("nan"), 0
    chi2 = -2 * sum(np.log(v) for v in valid)
    df = 2 * k
    combined_p = 1 - scipy_stats.chi2.cdf(chi2, df)
    return float(combined_p), k


def main():
    folds = generate_folds()
    dev_s = min(f.oos_start for f in folds)
    dev_e = max(f.oos_end for f in folds)
    ho_s = pd.Timestamp("2025-01-01", tz="UTC").value
    ho_e = pd.Timestamp("2026-10-19", tz="UTC").value
    fold_ho = Fold(fold_id=100, train_start=0, train_end=ho_s - 1, oos_start=ho_s, oos_end=ho_e)

    results_dev = []; results_ho = []
    for sym, slip in FX_PAIRS:
        print(f"\n=== {sym} ===", flush=True)
        cfg = Cfg(f"RSI2-{sym}-SYM-POOL", sym, 1)

        bars_dev = read_bars_d1(sym, "dev")
        if bars_dev.empty:
            print(f"  no dev bars for {sym}, skip"); continue
        all_dev = pd.concat([_collect_trades(bars_dev, slip, f) for f in folds], ignore_index=True)
        print(f"  DEV n={len(all_dev)} trades", flush=True)
        res_dev = _run_pair_scheme1(sym, slip, bars_dev, all_dev, dev_s, dev_e, cfg.engine_id, "dev")
        if res_dev:
            print(f"    obs_mean_r={res_dev['obs_mean_r']:+.4f} null_med={res_dev['null_mean_median']:+.4f} p={res_dev['p_mean_r']:.4f}", flush=True)
            results_dev.append(res_dev)

        bars_ho = read_bars_d1(sym, "holdout")
        if bars_ho.empty:
            print(f"  no holdout for {sym}, skip"); continue
        ho_trades = _collect_trades(bars_ho, slip, fold_ho)
        print(f"  HOLDOUT n={len(ho_trades)} trades", flush=True)
        res_ho = _run_pair_scheme1(sym, slip, bars_ho, ho_trades, ho_s, ho_e, cfg.engine_id, "ho")
        if res_ho:
            print(f"    obs_mean_r={res_ho['obs_mean_r']:+.4f} null_med={res_ho['null_mean_median']:+.4f} p={res_ho['p_mean_r']:.4f}", flush=True)
            results_ho.append(res_ho)

    print("\n=== Fisher-combined p-values ===", flush=True)
    comb_dev, k_dev = fisher_combine([r["p_mean_r"] for r in results_dev])
    comb_ho, k_ho = fisher_combine([r["p_mean_r"] for r in results_ho])
    print(f"  DEV:     combined p = {comb_dev:.6f}  (k={k_dev} pairs)   {'PASS' if comb_dev < ALPHA else 'FAIL'} alpha={ALPHA}")
    print(f"  HOLDOUT: combined p = {comb_ho:.6f}  (k={k_ho} pairs)   {'PASS' if comb_ho < ALPHA else 'FAIL'} alpha={ALPHA}")

    out = {
        "n_permutations": N_PERMUTATIONS, "alpha": ALPHA,
        "dev": {"per_pair": results_dev, "fisher_combined_p": comb_dev, "k": k_dev},
        "holdout": {"per_pair": results_ho, "fisher_combined_p": comb_ho, "k": k_ho},
    }
    out_path = Path("out/c4b_gates/fx_pooled_scheme1.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n[fx-pool] wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
