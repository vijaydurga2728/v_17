"""Exploration: run scheme-1 MCPT (mean_r + paired-alpha) on RSI2-GBPUSD.

NOT a formal cycle gate. Explicitly an exploration based on marginal dev
PF 1.129 / holdout PF 1.960 observed 2026-11-11. If scheme-1 passes,
candidate for addition to demo. If not, documented negative.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Patch slippage BEFORE importing anything that caches it.
from v17.backtest import rsi2_runner
from v17.validation import mcpt_scheme1

FX_SLIPPAGE = 0.00005  # 0.5 pips in GBPUSD price units
rsi2_runner.COST_SLIPPAGE_PTS_USATECH = FX_SLIPPAGE
mcpt_scheme1.COST_SLIPPAGE_PTS_USATECH = FX_SLIPPAGE

from v17.backtest.rsi2_runner import run_rsi2_oos_batch
from v17.backtest.rsi2_paired_runner import compute_paired_alpha, _alpha_metrics
from v17.backtest.engine_runner import _to_mid_bars
from v17.backtest.walkforward import Fold, generate_folds
from v17.data.parquet_store import read_bars_d1
from v17.setups.rsi2_constants import RSI_PERIOD_D1, SMA_EXIT_PERIOD_D1
from v17.validation.mcpt_scheme1 import run_scheme1_mcpt_rsi2
from v17.validation.seeds import permutation_seed

from dataclasses import dataclass

@dataclass(frozen=True)
class C:
    engine_id: str
    symbol: str
    priority_order: int


N_PERMUTATIONS = 500
ALPHA = 0.05
engine = C(engine_id="RSI2-GBPUSD-EXPLORATION", symbol="GBPUSD", priority_order=1)


def collect(part, win_start, win_end):
    bars = read_bars_d1(engine.symbol, part)
    if part == "dev":
        folds = generate_folds()
        win_start_ns = min(f.oos_start for f in folds)
        win_end_ns = max(f.oos_end for f in folds)
    else:
        folds = [Fold(fold_id=100, train_start=0, train_end=win_start - 1,
                      oos_start=win_start, oos_end=win_end)]
        win_start_ns, win_end_ns = win_start, win_end
    logs = run_rsi2_oos_batch(engine, bars, folds)
    trades = [t for l in logs for t in l.trades]
    return bars, pd.DataFrame(trades), win_start_ns, win_end_ns


def run_paired_null(bars, n_trades, avg_hold, win_start, win_end, label):
    mid = _to_mid_bars(bars).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    close = mid["close"].to_numpy()
    log_ret = np.diff(np.log(close), prepend=np.log(close[0]))
    in_window = (ts_ns >= win_start) & (ts_ns < win_end)
    n = len(mid)
    min_i = max(RSI_PERIOD_D1 + 1, SMA_EXIT_PERIOD_D1)
    max_i = n - avg_hold - 1
    eligible = np.where(in_window)[0]
    eligible = eligible[(eligible >= min_i) & (eligible <= max_i)]
    null_cum = np.full(N_PERMUTATIONS, np.nan)
    null_mean = np.full(N_PERMUTATIONS, np.nan)
    for p in range(N_PERMUTATIONS):
        seed = permutation_seed(engine.engine_id, f"paired_{label}", p)
        rng = np.random.default_rng(seed)
        sampled = rng.choice(eligible, size=n_trades, replace=False)
        active = np.zeros(n, dtype=bool)
        for ei in sampled:
            active[ei: ei + avg_hold] = True
        m = _alpha_metrics(active, log_ret, in_window)
        if m is None:
            continue
        null_cum[p] = m.observed_alpha_cum
        null_mean[p] = m.observed_alpha_mean
    return null_cum, null_mean


def main():
    print("[explore-gbp] DEV scheme-1 (mean_r variant)...", flush=True)
    bars_dev, dev_trades, dev_s, dev_e = collect("dev", None, None)
    print(f"  dev trades: {len(dev_trades)}", flush=True)
    res_dev = run_scheme1_mcpt_rsi2(
        engine_id=engine.engine_id, bars_d1=bars_dev,
        observed_trades=dev_trades, window_label="dev",
        window_start_ns=dev_s, window_end_ns=dev_e,
        n_permutations=N_PERMUTATIONS,
    )
    print(f"  observed mean_r: {res_dev.observed_mean_r:+.4f}", flush=True)
    print(f"  null mean_r: median={res_dev.null_mean_r_median:+.4f} mean={res_dev.null_mean_r_mean:+.4f} p95={res_dev.null_mean_r_p95:+.4f}", flush=True)
    print(f"  p_mean_r = {res_dev.p_mean_r:.4f} ({'PASS' if res_dev.p_mean_r < ALPHA else 'FAIL'})", flush=True)
    print(f"  p_pf    = {res_dev.p_pf:.4f}", flush=True)

    print("\n[explore-gbp] HOLDOUT scheme-1 (mean_r variant)...", flush=True)
    bars_ho, ho_trades, ho_s, ho_e = collect(
        "holdout",
        pd.Timestamp("2025-01-01", tz="UTC").value,
        pd.Timestamp("2026-10-19", tz="UTC").value,
    )
    print(f"  holdout trades: {len(ho_trades)}", flush=True)
    res_ho = run_scheme1_mcpt_rsi2(
        engine_id=engine.engine_id, bars_d1=bars_ho,
        observed_trades=ho_trades, window_label="holdout",
        window_start_ns=ho_s, window_end_ns=ho_e,
        n_permutations=N_PERMUTATIONS,
    )
    print(f"  observed mean_r: {res_ho.observed_mean_r:+.4f}", flush=True)
    print(f"  null mean_r: median={res_ho.null_mean_r_median:+.4f} mean={res_ho.null_mean_r_mean:+.4f} p95={res_ho.null_mean_r_p95:+.4f}", flush=True)
    print(f"  p_mean_r = {res_ho.p_mean_r:.4f} ({'PASS' if res_ho.p_mean_r < ALPHA else 'FAIL'})", flush=True)
    print(f"  p_pf    = {res_ho.p_pf:.4f}", flush=True)

    print("\n[explore-gbp] DEV paired-alpha...", flush=True)
    obs_dev = compute_paired_alpha(engine, bars_dev, generate_folds(), dev_s, dev_e)
    hold_i = int(round(obs_dev.avg_holding_bars))
    null_cum, null_mean = run_paired_null(bars_dev, obs_dev.n_trades, hold_i, dev_s, dev_e, "dev")
    p_cum_dev = float((null_cum >= obs_dev.observed_alpha_cum).mean())
    p_mean_pa_dev = float((null_mean >= obs_dev.observed_alpha_mean).mean())
    print(f"  obs alpha_cum={obs_dev.observed_alpha_cum:+.5f} alpha_mean={obs_dev.observed_alpha_mean:+.6f}", flush=True)
    print(f"  null_cum median={np.nanmedian(null_cum):+.5f}", flush=True)
    print(f"  p_cum = {p_cum_dev:.4f} ({'PASS' if p_cum_dev < ALPHA else 'FAIL'})", flush=True)
    print(f"  p_mean = {p_mean_pa_dev:.4f} ({'PASS' if p_mean_pa_dev < ALPHA else 'FAIL'})", flush=True)

    print("\n[explore-gbp] HOLDOUT paired-alpha...", flush=True)
    obs_ho = compute_paired_alpha(engine, bars_ho, [Fold(100, 0, ho_s - 1, ho_s, ho_e)], ho_s, ho_e)
    hold_i_ho = int(round(obs_ho.avg_holding_bars))
    null_cum_ho, null_mean_ho = run_paired_null(bars_ho, obs_ho.n_trades, hold_i_ho, ho_s, ho_e, "holdout")
    p_cum_ho = float((null_cum_ho >= obs_ho.observed_alpha_cum).mean())
    p_mean_pa_ho = float((null_mean_ho >= obs_ho.observed_alpha_mean).mean())
    print(f"  obs alpha_cum={obs_ho.observed_alpha_cum:+.5f} alpha_mean={obs_ho.observed_alpha_mean:+.6f}", flush=True)
    print(f"  null_cum median={np.nanmedian(null_cum_ho):+.5f}", flush=True)
    print(f"  p_cum = {p_cum_ho:.4f} ({'PASS' if p_cum_ho < ALPHA else 'FAIL'})", flush=True)
    print(f"  p_mean = {p_mean_pa_ho:.4f} ({'PASS' if p_mean_pa_ho < ALPHA else 'FAIL'})", flush=True)

    summary = {
        "engine": engine.engine_id,
        "n_permutations": N_PERMUTATIONS, "alpha": ALPHA,
        "scheme1_mean_r": {
            "dev": {"observed": res_dev.observed_mean_r, "p_mean_r": res_dev.p_mean_r, "p_pf": res_dev.p_pf,
                    "null_median": res_dev.null_mean_r_median},
            "holdout": {"observed": res_ho.observed_mean_r, "p_mean_r": res_ho.p_mean_r, "p_pf": res_ho.p_pf,
                        "null_median": res_ho.null_mean_r_median},
        },
        "paired_alpha": {
            "dev": {"alpha_cum": obs_dev.observed_alpha_cum, "p_cum": p_cum_dev, "p_mean": p_mean_pa_dev,
                    "null_cum_median": float(np.nanmedian(null_cum))},
            "holdout": {"alpha_cum": obs_ho.observed_alpha_cum, "p_cum": p_cum_ho, "p_mean": p_mean_pa_ho,
                        "null_cum_median": float(np.nanmedian(null_cum_ho))},
        },
        "verdict": {
            "mean_r_both_pass": res_dev.p_mean_r < ALPHA and res_ho.p_mean_r < ALPHA,
            "paired_both_pass": p_cum_dev < ALPHA and p_cum_ho < ALPHA,
        },
    }
    out = Path("out/c4b_gates/gbp_scheme1_exploration.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(f"\n[explore-gbp] wrote {out}", flush=True)


if __name__ == "__main__":
    main()
