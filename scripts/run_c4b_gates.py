"""Cycle 4B formal gates — per-pair G1-G5, cost-stress, MCPT (Bonferroni α=0.00714).

7 pairs: TSM x3, Donchian x3, RSI2 x1 (all D1).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.walkforward import generate_folds
from v17.data.parquet_store import read_bars_d1
from v17.validation.mcpt_runner import run_mcpt
from v17.validation.secondary_gates import evaluate_secondary

from v17.backtest.tsm_runner import run_tsm_oos_batch
from v17.backtest.donchian_runner import run_donchian_oos_batch
from v17.backtest.rsi2_runner import run_rsi2_oos_batch
from v17.setups.tsm_engines import TSM_CATALOG
from v17.setups.donchian_engines import DONCHIAN_CATALOG
from v17.setups.rsi2_engines import RSI2_CATALOG

from v17.setups import tsm_constants as tsm_c
from v17.setups import donchian_constants as don_c
from v17.setups import rsi2_constants as rsi_c


BONFERRONI_ALPHA = 0.05 / 7
N_PERMUTATIONS = 500


def _run_engine(engine_id: str, engine, folds, bars):
    if engine_id.startswith("TSM-"):
        return run_tsm_oos_batch(engine, bars, folds)
    if engine_id.startswith("DON-"):
        return run_donchian_oos_batch(engine, bars, folds)
    if engine_id.startswith("RSI2-"):
        return run_rsi2_oos_batch(engine, bars, folds)
    raise ValueError(f"Unknown engine family: {engine_id!r}")


def _trades_df(logs) -> pd.DataFrame:
    rows = [t for l in logs for t in l.trades]
    if not rows:
        return pd.DataFrame(columns=["pnl_r", "ts_entry_ns", "fold_id"])
    df = pd.DataFrame(rows)
    return df


def _stress_slippage_apply(factor: float):
    """Monkey-patch all slippage constants by `factor`. Return the undo closure."""
    tsm_orig = dict(tsm_c.COST_SLIPPAGE_PTS)
    tsm_fx_orig = tsm_c.COST_SLIPPAGE_PIPS_FX
    don_orig = dict(don_c.COST_SLIPPAGE_PTS)
    don_fx_orig = don_c.COST_SLIPPAGE_PIPS_FX
    rsi_orig = rsi_c.COST_SLIPPAGE_PTS_USATECH

    for k in list(tsm_c.COST_SLIPPAGE_PTS):
        tsm_c.COST_SLIPPAGE_PTS[k] *= factor
    tsm_c.COST_SLIPPAGE_PIPS_FX *= factor
    for k in list(don_c.COST_SLIPPAGE_PTS):
        don_c.COST_SLIPPAGE_PTS[k] *= factor
    don_c.COST_SLIPPAGE_PIPS_FX *= factor
    rsi_c.COST_SLIPPAGE_PTS_USATECH *= factor

    def undo():
        tsm_c.COST_SLIPPAGE_PTS.clear()
        tsm_c.COST_SLIPPAGE_PTS.update(tsm_orig)
        tsm_c.COST_SLIPPAGE_PIPS_FX = tsm_fx_orig
        don_c.COST_SLIPPAGE_PTS.clear()
        don_c.COST_SLIPPAGE_PTS.update(don_orig)
        don_c.COST_SLIPPAGE_PIPS_FX = don_fx_orig
        rsi_c.COST_SLIPPAGE_PTS_USATECH = rsi_orig

    return undo


def _pf(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    pnl = trades["pnl_r"].to_numpy()
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    return float(wins / losses) if losses > 0 else float("inf")


def main() -> None:
    folds = generate_folds()
    out_dir = Path("out/c4b_gates")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_engines: list = []
    for e in TSM_CATALOG:
        all_engines.append(("TSM", e))
    for e in DONCHIAN_CATALOG:
        all_engines.append(("DON", e))
    for e in RSI2_CATALOG:
        all_engines.append(("RSI2", e))

    bars_cache: dict[str, pd.DataFrame] = {}
    for _, engine in all_engines:
        if engine.symbol not in bars_cache:
            bars_cache[engine.symbol] = read_bars_d1(engine.symbol, "dev")

    results: list[dict] = []

    for family, engine in all_engines:
        eid = engine.engine_id
        print(f"\n[c4b] === {eid} ===", flush=True)
        bars = bars_cache[engine.symbol]

        # Base run.
        logs = _run_engine(eid, engine, folds, bars)
        trades = _trades_df(logs)
        print(f"[c4b] base trades: {len(trades)}", flush=True)

        if trades.empty:
            results.append({"engine_id": eid, "verdict": "NO_TRADES"})
            continue

        min_trade = 25 if family == "RSI2" else 25
        base_pf = _pf(trades)

        # Cost stress: 2x slippage.
        undo = _stress_slippage_apply(2.0)
        try:
            stress_logs = _run_engine(eid, engine, folds, bars)
            stress_trades = _trades_df(stress_logs)
            stress_pf = _pf(stress_trades) if not stress_trades.empty else 0.0
        finally:
            undo()
        print(f"[c4b] stress PF (2x slip): {stress_pf:.3f}", flush=True)

        report = evaluate_secondary(trades, cost_stress_pf=stress_pf, min_trade_count=min_trade)
        print(f"[c4b] gates G1={report.G1_pass} G2={report.G2_pass} G3={report.G3_pass} G4={report.G4_pass} G5={report.G5_pass}", flush=True)

        # MCPT (pnl_bootstrap).
        print(f"[c4b] running MCPT {N_PERMUTATIONS} permutations...", flush=True)
        mcpt = run_mcpt(
            engine_id=eid, trades=trades, bars=bars,
            calendar=pd.DataFrame(columns=["timestamp_utc", "currency", "impact"]),
            scheme="pnl_bootstrap", n_permutations=N_PERMUTATIONS, out_root=out_dir,
        )
        mcpt_pass = (mcpt["p_pf"] < BONFERRONI_ALPHA) if np.isfinite(mcpt["p_pf"]) else False
        print(f"[c4b] MCPT p_pf={mcpt['p_pf']:.4f} (alpha={BONFERRONI_ALPHA:.5f}) pass={mcpt_pass}", flush=True)

        verdict = "ADVANCE" if (report.all_pass and mcpt_pass) else "SHELVE"
        results.append({
            "engine_id": eid,
            "trades": int(report.details["trade_count"]),
            "pf": float(report.details["pf"]),
            "r2": float(report.details["r2"]),
            "stress_pf": float(stress_pf),
            "G1": bool(report.G1_pass),
            "G2": bool(report.G2_pass),
            "G3": bool(report.G3_pass),
            "G4": bool(report.G4_pass),
            "G5": bool(report.G5_pass),
            "all_gates": bool(report.all_pass),
            "mcpt_p_pf": float(mcpt["p_pf"]) if np.isfinite(mcpt["p_pf"]) else None,
            "mcpt_pass": bool(mcpt_pass),
            "verdict": verdict,
            "per_fold": {int(k): float(v) for k, v in report.details["per_fold"].items()},
        })

    # Write JSON summary.
    out_json = out_dir / "c4b_gate_summary.json"
    out_json.write_text(json.dumps({"alpha": BONFERRONI_ALPHA, "results": results}, indent=2))
    print(f"\n[c4b] wrote {out_json}", flush=True)

    # Markdown report.
    md = ["# Cycle 4B Formal Gate Report — 2026-11-11", ""]
    md.append(f"- Bonferroni alpha (7 pairs): **{BONFERRONI_ALPHA:.5f}**")
    md.append(f"- MCPT permutations: {N_PERMUTATIONS}, scheme pnl_bootstrap, block_size 5")
    md.append(f"- G2 relaxed-floor: 25 trades")
    md.append("")
    md.append("| Engine | Trades | PF | R² | Stress PF | G1 | G2 | G3 | G4 | G5 | MCPT p_pf | Verdict |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        if r.get("verdict") == "NO_TRADES":
            md.append(f"| {r['engine_id']} | 0 | — | — | — | — | — | — | — | — | — | NO_TRADES |")
            continue
        md.append(
            f"| {r['engine_id']} | {r['trades']} | {r['pf']:.3f} | {r['r2']:.3f} | "
            f"{r['stress_pf']:.3f} | {'P' if r['G1'] else 'F'} | {'P' if r['G2'] else 'F'} | "
            f"{'P' if r['G3'] else 'F'} | {'P' if r['G4'] else 'F'} | {'P' if r['G5'] else 'F'} | "
            f"{r['mcpt_p_pf']:.4f} | **{r['verdict']}** |"
        )
    advancers = [r['engine_id'] for r in results if r.get('verdict') == 'ADVANCE']
    md.append("")
    md.append(f"### Pairs advancing to holdout: {advancers if advancers else 'NONE'}")
    out_md = Path("docs/superpowers/plans/c4b_gate_report_2026-11-11.md")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"[c4b] wrote {out_md}", flush=True)


if __name__ == "__main__":
    main()
