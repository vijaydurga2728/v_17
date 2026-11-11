"""Run scheme-1 MCPT for RSI2-NAS100 on dev + holdout.

Random-entry null per docs/superpowers/specs/2026-11-11-cycle4b-mcpt-scheme-addendum.md.
Required gate before live money: p_pf < 0.05 (single pair, no Bonferroni).
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.rsi2_runner import run_rsi2_oos_batch
from v17.backtest.walkforward import Fold, generate_folds
from v17.data.parquet_store import read_bars_d1
from v17.setups.rsi2_engines import RSI2_CATALOG
from v17.validation.mcpt_scheme1 import run_scheme1_mcpt_rsi2


N_PERMUTATIONS = 500
ALPHA_SINGLE = 0.05


def _collect_trades(bars, folds, engine) -> pd.DataFrame:
    logs = run_rsi2_oos_batch(engine, bars, folds)
    rows = [t for l in logs for t in l.trades]
    if not rows:
        return pd.DataFrame(columns=["pnl_r", "ts_entry_ns"])
    return pd.DataFrame(rows)


def main() -> None:
    engine = RSI2_CATALOG[0]
    out_root = Path("out/c4b_gates")
    out_root.mkdir(parents=True, exist_ok=True)

    # --- DEV window ---
    print(f"[c4b-s1] loading dev bars", flush=True)
    bars_dev = read_bars_d1(engine.symbol, "dev")
    folds = generate_folds()
    dev_trades = _collect_trades(bars_dev, folds, engine)
    print(f"[c4b-s1] dev trades: {len(dev_trades)}", flush=True)

    dev_start = min(f.oos_start for f in folds)
    dev_end = max(f.oos_end for f in folds)
    print(f"[c4b-s1] running scheme-1 MCPT on DEV ({N_PERMUTATIONS} perms)...", flush=True)
    res_dev = run_scheme1_mcpt_rsi2(
        engine_id=engine.engine_id, bars_d1=bars_dev, observed_trades=dev_trades,
        window_label="dev", window_start_ns=dev_start, window_end_ns=dev_end,
        n_permutations=N_PERMUTATIONS, out_root=out_root,
    )
    print(f"[c4b-s1] DEV: observed_pf={res_dev.observed_pf:.3f} p_pf={res_dev.p_pf:.4f}", flush=True)
    print(f"[c4b-s1]       null median={res_dev.null_pf_median:.3f} mean={res_dev.null_pf_mean:.3f} p95={res_dev.null_pf_p95:.3f}", flush=True)

    # --- HOLDOUT window ---
    print(f"[c4b-s1] loading holdout bars", flush=True)
    bars_ho = read_bars_d1(engine.symbol, "holdout")
    ho_start = pd.Timestamp("2025-01-01", tz="UTC").value
    ho_end = pd.Timestamp("2026-10-19", tz="UTC").value
    fold_ho = Fold(fold_id=100, train_start=0, train_end=ho_start - 1,
                   oos_start=ho_start, oos_end=ho_end)
    ho_trades = _collect_trades(bars_ho, [fold_ho], engine)
    print(f"[c4b-s1] holdout trades: {len(ho_trades)}", flush=True)
    print(f"[c4b-s1] running scheme-1 MCPT on HOLDOUT ({N_PERMUTATIONS} perms)...", flush=True)
    res_ho = run_scheme1_mcpt_rsi2(
        engine_id=engine.engine_id, bars_d1=bars_ho, observed_trades=ho_trades,
        window_label="holdout", window_start_ns=ho_start, window_end_ns=ho_end,
        n_permutations=N_PERMUTATIONS, out_root=out_root,
    )
    print(f"[c4b-s1] HOLDOUT: observed_pf={res_ho.observed_pf:.3f} p_pf={res_ho.p_pf:.4f}", flush=True)
    print(f"[c4b-s1]            null median={res_ho.null_pf_median:.3f} mean={res_ho.null_pf_mean:.3f} p95={res_ho.null_pf_p95:.3f}", flush=True)

    # Report.
    pass_dev = res_dev.p_pf < ALPHA_SINGLE
    pass_ho = res_ho.p_pf < ALPHA_SINGLE

    md = [
        "# RSI2-USATECHIDXUSD Scheme-1 MCPT Report — 2026-11-11",
        "",
        "**Required gate before live money** per `2026-11-11-cycle4b-mcpt-scheme-addendum.md`.",
        f"**Permutations:** {N_PERMUTATIONS}. **Alpha (single pair):** {ALPHA_SINGLE}.",
        "**Null model:** random long-only entries uniformly sampled from eligible D1 bars in window.",
        "",
        "## Dev window (2018-01-01 → 2025-01-01, 7 folds union)",
        "",
        f"- Observed PF: **{res_dev.observed_pf:.3f}** over {res_dev.n_obs_trades} trades.",
        f"- Null PF — median {res_dev.null_pf_median:.3f}, mean {res_dev.null_pf_mean:.3f}, p95 {res_dev.null_pf_p95:.3f}.",
        f"- **p_pf = {res_dev.p_pf:.4f}** ({'PASS' if pass_dev else 'FAIL'} vs alpha {ALPHA_SINGLE}).",
        "",
        "## Holdout window (2025-01-01 → 2026-10-18)",
        "",
        f"- Observed PF: **{res_ho.observed_pf:.3f}** over {res_ho.n_obs_trades} trades.",
        f"- Null PF — median {res_ho.null_pf_median:.3f}, mean {res_ho.null_pf_mean:.3f}, p95 {res_ho.null_pf_p95:.3f}.",
        f"- **p_pf = {res_ho.p_pf:.4f}** ({'PASS' if pass_ho else 'FAIL'} vs alpha {ALPHA_SINGLE}).",
        "",
        "## Combined verdict",
        "",
        f"- Dev pass: **{pass_dev}**. Holdout pass: **{pass_ho}**.",
        f"- Both required for live-money clearance.",
        "",
        f"### Status: {'LIVE-CLEARED (both pass)' if (pass_dev and pass_ho) else ('HOLDOUT-ONLY-PASS' if pass_ho and not pass_dev else 'DEV-ONLY-PASS' if pass_dev and not pass_ho else 'SHELVE (both fail scheme-1)')}",
    ]
    out_md = Path("docs/superpowers/plans/c4b_scheme1_mcpt_report_2026-11-11.md")
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"[c4b-s1] wrote {out_md}", flush=True)

    # JSON
    summary = {
        "n_permutations": N_PERMUTATIONS, "alpha_single": ALPHA_SINGLE,
        "dev": {**{k: v for k, v in asdict(res_dev).items()}, "pass": pass_dev},
        "holdout": {**{k: v for k, v in asdict(res_ho).items()}, "pass": pass_ho},
        "combined_live_cleared": bool(pass_dev and pass_ho),
    }
    (out_root / "scheme1_mcpt_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
