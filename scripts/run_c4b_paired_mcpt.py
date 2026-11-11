"""Paired-alpha scheme-1 MCPT for RSI2-NAS100.

Independent-confirmation test: computes daily alpha stream against
constant-exposure benchmark (see rsi2_paired_runner.py). Compares
observed cumulative/mean/PF alpha to random-entry null distribution.

Null construction:
  - Preserve n_trades and avg_holding_bars from observed.
  - For each permutation, sample n_trades random entry indices from
    eligible pool (same as scheme-1 base). Build synthetic active_pos
    using the observed avg_holding_bars as the fixed holding window.
  - Compute null alpha_cum, alpha_mean, alpha_pf on that synthetic series.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.engine_runner import _to_mid_bars
from v17.backtest.rsi2_paired_runner import _alpha_metrics, compute_paired_alpha
from v17.backtest.walkforward import Fold, generate_folds
from v17.data.parquet_store import read_bars_d1
from v17.setups.rsi2_constants import RSI_PERIOD_D1, SMA_EXIT_PERIOD_D1
from v17.setups.rsi2_engines import RSI2_CATALOG
from v17.validation.seeds import permutation_seed


N_PERMUTATIONS = 500
ALPHA = 0.05


def run_null_distribution(
    engine_id: str, window_label: str, bars_d1: pd.DataFrame,
    n_trades: int, avg_holding: int,
    window_start_ns: int, window_end_ns: int, n_perm: int,
) -> dict:
    mid = _to_mid_bars(bars_d1).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    close = mid["close"].to_numpy()
    log_ret = np.diff(np.log(close), prepend=np.log(close[0]))
    in_window = (ts_ns >= window_start_ns) & (ts_ns < window_end_ns)

    n = len(mid)
    min_i = max(RSI_PERIOD_D1 + 1, SMA_EXIT_PERIOD_D1)
    max_i = n - avg_holding - 1
    eligible = np.where(in_window)[0]
    eligible = eligible[(eligible >= min_i) & (eligible <= max_i)]
    if len(eligible) < n_trades:
        raise ValueError(f"eligible pool {len(eligible)} < n_trades {n_trades}")

    null_cum = np.full(n_perm, np.nan)
    null_mean = np.full(n_perm, np.nan)
    null_pf = np.full(n_perm, np.nan)
    for p in range(n_perm):
        seed = permutation_seed(engine_id, f"paired_{window_label}", p)
        rng = np.random.default_rng(seed)
        sampled = rng.choice(eligible, size=n_trades, replace=False)
        active = np.zeros(n, dtype=bool)
        for ei in sampled:
            active[ei: ei + avg_holding] = True
        m = _alpha_metrics(active, log_ret, in_window)
        if m is None:
            continue
        null_cum[p] = m.observed_alpha_cum
        null_mean[p] = m.observed_alpha_mean
        null_pf[p] = m.observed_alpha_pf if np.isfinite(m.observed_alpha_pf) else np.nan
    return {"cum": null_cum, "mean": null_mean, "pf": null_pf}


def main() -> None:
    engine = RSI2_CATALOG[0]
    folds = generate_folds()
    out_root = Path("out/c4b_gates")
    out_root.mkdir(parents=True, exist_ok=True)

    # DEV
    print("[c4b-paired] loading dev bars", flush=True)
    bars_dev = read_bars_d1(engine.symbol, "dev")
    dev_start = min(f.oos_start for f in folds)
    dev_end = max(f.oos_end for f in folds)
    obs_dev = compute_paired_alpha(engine, bars_dev, folds, dev_start, dev_end)
    print(f"[c4b-paired] DEV observed: cum={obs_dev.observed_alpha_cum:.5f} mean={obs_dev.observed_alpha_mean:.6f} pf={obs_dev.observed_alpha_pf:.3f}", flush=True)
    print(f"[c4b-paired]   trades={obs_dev.n_trades} avg_hold={obs_dev.avg_holding_bars:.1f} exposure={obs_dev.exposure_frac:.3f}", flush=True)

    hold_i = int(round(obs_dev.avg_holding_bars))
    print(f"[c4b-paired] running DEV null ({N_PERMUTATIONS} perms, hold={hold_i})...", flush=True)
    null_dev = run_null_distribution(
        engine.engine_id, "dev", bars_dev, obs_dev.n_trades, hold_i,
        dev_start, dev_end, N_PERMUTATIONS,
    )
    p_cum_dev = float((null_dev["cum"] >= obs_dev.observed_alpha_cum).mean())
    p_mean_dev = float((null_dev["mean"] >= obs_dev.observed_alpha_mean).mean())
    finite_pf = null_dev["pf"][np.isfinite(null_dev["pf"])]
    p_pf_dev = float((finite_pf >= obs_dev.observed_alpha_pf).mean()) if len(finite_pf) else float("nan")
    print(f"[c4b-paired] DEV p_cum={p_cum_dev:.4f} p_mean={p_mean_dev:.4f} p_pf={p_pf_dev:.4f}", flush=True)
    print(f"[c4b-paired]   null_cum median={np.nanmedian(null_dev['cum']):.5f} p95={np.nanpercentile(null_dev['cum'],95):.5f}", flush=True)

    # HOLDOUT
    print("[c4b-paired] loading holdout bars", flush=True)
    bars_ho = read_bars_d1(engine.symbol, "holdout")
    ho_start = pd.Timestamp("2025-01-01", tz="UTC").value
    ho_end = pd.Timestamp("2026-10-19", tz="UTC").value
    fold_ho = Fold(fold_id=100, train_start=0, train_end=ho_start - 1,
                   oos_start=ho_start, oos_end=ho_end)
    obs_ho = compute_paired_alpha(engine, bars_ho, [fold_ho], ho_start, ho_end)
    print(f"[c4b-paired] HOLDOUT observed: cum={obs_ho.observed_alpha_cum:.5f} mean={obs_ho.observed_alpha_mean:.6f} pf={obs_ho.observed_alpha_pf:.3f}", flush=True)
    print(f"[c4b-paired]   trades={obs_ho.n_trades} avg_hold={obs_ho.avg_holding_bars:.1f} exposure={obs_ho.exposure_frac:.3f}", flush=True)

    hold_i_ho = int(round(obs_ho.avg_holding_bars))
    print(f"[c4b-paired] running HOLDOUT null ({N_PERMUTATIONS} perms, hold={hold_i_ho})...", flush=True)
    null_ho = run_null_distribution(
        engine.engine_id, "holdout", bars_ho, obs_ho.n_trades, hold_i_ho,
        ho_start, ho_end, N_PERMUTATIONS,
    )
    p_cum_ho = float((null_ho["cum"] >= obs_ho.observed_alpha_cum).mean())
    p_mean_ho = float((null_ho["mean"] >= obs_ho.observed_alpha_mean).mean())
    finite_pf_ho = null_ho["pf"][np.isfinite(null_ho["pf"])]
    p_pf_ho = float((finite_pf_ho >= obs_ho.observed_alpha_pf).mean()) if len(finite_pf_ho) else float("nan")
    print(f"[c4b-paired] HOLDOUT p_cum={p_cum_ho:.4f} p_mean={p_mean_ho:.4f} p_pf={p_pf_ho:.4f}", flush=True)
    print(f"[c4b-paired]   null_cum median={np.nanmedian(null_ho['cum']):.5f} p95={np.nanpercentile(null_ho['cum'],95):.5f}", flush=True)

    # Report
    pass_dev = p_cum_dev < ALPHA and p_mean_dev < ALPHA
    pass_ho = p_cum_ho < ALPHA and p_mean_ho < ALPHA
    md = [
        "# RSI2-USATECHIDXUSD Paired-Alpha Scheme-1 MCPT Report — 2026-11-11",
        "",
        "Independent-confirmation test alongside per-trade mean_r scheme-1.",
        f"Permutations: {N_PERMUTATIONS}. Alpha: {ALPHA}.",
        "",
        "## Construction",
        "",
        "- active_pos_t = 1 while in RSI(2) trade, 0 flat.",
        "- exposure_frac = mean(active_pos).",
        "- alpha_t = (active_pos_t - exposure_frac) * log_return_t.",
        "- Null: random entry days, same count and avg_holding, same alpha formula.",
        "",
        "## Dev window",
        "",
        f"- Observed: cum={obs_dev.observed_alpha_cum:.5f} mean={obs_dev.observed_alpha_mean:.6f} pf={obs_dev.observed_alpha_pf:.3f}",
        f"- Trades {obs_dev.n_trades}, avg hold {obs_dev.avg_holding_bars:.1f}, exposure {obs_dev.exposure_frac:.3f}",
        f"- p_cum = **{p_cum_dev:.4f}** ({'PASS' if p_cum_dev < ALPHA else 'FAIL'})",
        f"- p_mean = **{p_mean_dev:.4f}** ({'PASS' if p_mean_dev < ALPHA else 'FAIL'})",
        f"- p_pf = {p_pf_dev:.4f}",
        "",
        "## Holdout window",
        "",
        f"- Observed: cum={obs_ho.observed_alpha_cum:.5f} mean={obs_ho.observed_alpha_mean:.6f} pf={obs_ho.observed_alpha_pf:.3f}",
        f"- Trades {obs_ho.n_trades}, avg hold {obs_ho.avg_holding_bars:.1f}, exposure {obs_ho.exposure_frac:.3f}",
        f"- p_cum = **{p_cum_ho:.4f}** ({'PASS' if p_cum_ho < ALPHA else 'FAIL'})",
        f"- p_mean = **{p_mean_ho:.4f}** ({'PASS' if p_mean_ho < ALPHA else 'FAIL'})",
        f"- p_pf = {p_pf_ho:.4f}",
        "",
        "## Verdict",
        "",
        f"- Dev independent-confirmation pass: **{pass_dev}**",
        f"- Holdout independent-confirmation pass: **{pass_ho}**",
    ]
    out_md = Path("docs/superpowers/plans/c4b_paired_mcpt_report_2026-11-11.md")
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"[c4b-paired] wrote {out_md}", flush=True)

    summary = {
        "n_permutations": N_PERMUTATIONS, "alpha": ALPHA,
        "dev": {
            "alpha_cum": obs_dev.observed_alpha_cum,
            "alpha_mean": obs_dev.observed_alpha_mean,
            "alpha_pf": obs_dev.observed_alpha_pf,
            "n_trades": obs_dev.n_trades, "avg_holding": obs_dev.avg_holding_bars,
            "exposure": obs_dev.exposure_frac,
            "p_cum": p_cum_dev, "p_mean": p_mean_dev, "p_pf": p_pf_dev,
            "pass": pass_dev,
        },
        "holdout": {
            "alpha_cum": obs_ho.observed_alpha_cum,
            "alpha_mean": obs_ho.observed_alpha_mean,
            "alpha_pf": obs_ho.observed_alpha_pf,
            "n_trades": obs_ho.n_trades, "avg_holding": obs_ho.avg_holding_bars,
            "exposure": obs_ho.exposure_frac,
            "p_cum": p_cum_ho, "p_mean": p_mean_ho, "p_pf": p_pf_ho,
            "pass": pass_ho,
        },
        "combined_pass": bool(pass_dev and pass_ho),
    }
    (out_root / "paired_mcpt_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
