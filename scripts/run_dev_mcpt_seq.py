"""Sequential-only dev MCPT run. Bypasses ProcessPoolExecutor (which was dying
silently on Windows). Uses run_engine_oos_batch in-process."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from v17.backtest.engine_runner import run_engine_oos_batch
from v17.backtest.walkforward import generate_folds
from v17.data.parquet_store import read_bars
from v17.setups.sb_engines import ENGINE_CATALOG
from v17.validation.mcpt_runner import run_mcpt
from v17.validation.secondary_gates import evaluate_secondary


ALPHA = 0.05 / 6  # 0.00833 Bonferroni


def _empty_cal() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"),
        "currency": pd.array([], dtype=object),
        "impact": pd.array([], dtype=object),
    })


def main() -> None:
    results_root = Path("research/results")
    results_root.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    folds = generate_folds()
    cal_path = Path("data") / "calendar" / "economic_events.parquet"
    calendar = pd.read_parquet(cal_path) if cal_path.exists() else _empty_cal()

    print(f"[{time.strftime('%H:%M:%S')}] Phase 1/3 — WF orchestrator sequential", flush=True)
    for engine in ENGINE_CATALOG:
        t_eng = time.time()
        frames = []
        for symbol in engine.symbols:
            sb = read_bars(root=Path("data"), symbol=symbol, partition="dev", dev_only=True)
            frames.append(sb)
        bars = pd.concat(frames, ignore_index=True)
        print(f"  [{time.strftime('%H:%M:%S')}] {engine.engine_id} bars: {len(bars):,} rows", flush=True)

        fold_logs = run_engine_oos_batch(
            config=engine, bars=bars, calendar=calendar, folds=folds
        )
        all_trades: list[dict] = []
        for log in fold_logs:
            for t in log.trades:
                if isinstance(t, dict):
                    rec = {
                        "engine_id": engine.engine_id,
                        "fold_id": log.fold_id,
                        **{k: t.get(k) for k in (
                            "symbol", "side", "ts_entry_ns", "entry_price",
                            "sl_price", "tp_price", "r_multiple",
                            "fvg_top", "fvg_bottom",
                            "exit_reason", "exit_price", "pnl_r", "pnl_cash",
                        )},
                    }
                else:
                    rec = {
                        "engine_id": engine.engine_id, "fold_id": log.fold_id,
                        "symbol": t.symbol, "side": t.side,
                        "ts_entry_ns": t.ts_entry_ns, "entry_price": t.entry_price,
                        "sl_price": t.sl_price, "tp_price": t.tp_price,
                        "r_multiple": t.r_multiple,
                        "fvg_top": t.fvg_top, "fvg_bottom": t.fvg_bottom,
                        "exit_reason": None, "exit_price": None,
                        "pnl_r": None, "pnl_cash": None,
                    }
                all_trades.append(rec)
        out = results_root / "wf" / engine.engine_id / "trades.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(all_trades).to_parquet(out, index=False)
        print(f"  [{time.strftime('%H:%M:%S')}] {engine.engine_id} done: "
              f"{len(all_trades)} trades, {time.time()-t_eng:.1f}s", flush=True)

    print(f"[{time.strftime('%H:%M:%S')}] Phase 2/3 — MCPT pnl_bootstrap", flush=True)
    rows: list[dict] = []
    for engine in ENGINE_CATALOG:
        tp = results_root / "wf" / engine.engine_id / "trades.parquet"
        if not tp.exists():
            continue
        tr = pd.read_parquet(tp)
        tc = len(tr)
        print(f"  {engine.engine_id}: {tc} trades", flush=True)
        if tc == 0 or "pnl_r" not in tr.columns or tr["pnl_r"].isna().all():
            rows.append({
                "engine_id": engine.engine_id, "trade_count": tc,
                "observed_sharpe": None, "observed_pf": None,
                "p_sharpe": None, "p_pf": None,
                "secondary_all_pass": False,
                "VERDICT": "INCONCLUSIVE_NO_PNL" if tc > 0 else "INCONCLUSIVE_NO_TRADES",
            })
            continue
        res = run_mcpt(
            engine_id=engine.engine_id, trades=tr, bars=pd.DataFrame(),
            calendar=pd.DataFrame(), scheme="pnl_bootstrap",
            n_permutations=1000, out_root=results_root,
        )
        cost_stress = res["observed_pf"] if res["observed_pf"] is not None else 0.0
        gate = evaluate_secondary(tr, cost_stress_pf=cost_stress)
        passes_mcpt = (
            res["p_sharpe"] is not None and res["p_sharpe"] < ALPHA
            and res["p_pf"] is not None and res["p_pf"] < ALPHA
        )
        rows.append({
            "engine_id": engine.engine_id, "trade_count": tc,
            "win_rate": float((tr["pnl_r"] > 0).mean()),
            "observed_sharpe": res["observed_sharpe"],
            "observed_pf": res["observed_pf"],
            "p_sharpe": res["p_sharpe"], "p_pf": res["p_pf"],
            "G1_pf": gate.G1_pass, "G2_count": gate.G2_pass,
            "G3_folds": gate.G3_pass, "G4_r2": gate.G4_pass,
            "G5_cost": gate.G5_pass, "secondary_all_pass": gate.all_pass,
            "VERDICT": "PASS" if (passes_mcpt and gate.all_pass) else "FAIL",
        })

    total = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Phase 3/3 — Writing verdicts  (total {total:.0f}s)")
    (results_root / "dev_mcpt_verdicts.json").write_text(json.dumps(rows, indent=2, default=str))
    print(json.dumps(rows, indent=2, default=str))
    print(f"Total wall-clock: {total:.0f}s ({total/60:.1f} min)", flush=True)


if __name__ == "__main__":
    main()
