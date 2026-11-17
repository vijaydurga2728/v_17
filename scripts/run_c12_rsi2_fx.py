"""Cycle 12: RSI(2) on 7 FX majors, variants L and S (pre-reg d8bd7fd). Writes out/c12/."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.backtest.rsi2_runner import run_rsi2_oos_batch  # noqa: E402
from v17.backtest.walkforward import Fold  # noqa: E402
from v17.data.parquet_store import read_bars  # noqa: E402
from v17.setups import c12_rsi2_fx as c12  # noqa: E402
from v17.setups.rsi2_engines import RSI2EngineConfig  # noqa: E402
from v17.validation.secondary_gates import evaluate_secondary  # noqa: E402

OUT = REPO / "out" / "c12"
M1_ROOT = REPO / ".worktrees" / "sb-6-engine-gate" / "data"
CACHE = REPO / "data" / "bars_d1_fxny"
DEV = (pd.Timestamp("2018-01-01").value, pd.Timestamp("2025-01-01").value)
HO_START = pd.Timestamp("2025-01-01").value
ALPHA = 0.05 / 14
N_PERMS = 10_000
SEED_BASE = 20261117 * 1_000 + 200


def load_d1(pair: str) -> pd.DataFrame:
    f = CACHE / pair / "d1.parquet"
    if f.exists():
        return pd.read_parquet(f)
    m1 = pd.concat([read_bars(root=M1_ROOT, symbol=pair, partition=part, dev_only=part == "dev")
                    for part in ("dev", "holdout")], ignore_index=True)
    m1 = m1.drop_duplicates("ts_utc").sort_values("ts_utc")
    d1 = c12.build_fxny_d1(m1)
    f.parent.mkdir(parents=True, exist_ok=True)
    d1.to_parquet(f, index=False)
    return d1


def stats(r: np.ndarray) -> dict[str, float]:
    loss = -r[r < 0].sum()
    eq = np.r_[0.0, np.cumsum(r)]
    return {"pf": float(r[r > 0].sum() / loss) if loss > 0 else float("inf"),
            "mean_r": float(r.mean()) if len(r) else 0.0,
            "win_rate": float((r > 0).mean()) if len(r) else 0.0,
            "max_dd_r": float((np.maximum.accumulate(eq) - eq).max())}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "trades").mkdir(exist_ok=True)
    audit, dev_rows, ho_rows = {}, [], []
    for k, (pair, var) in enumerate(c12.slots()):
        d1 = load_d1(pair)
        p = c12.prepare(d1)
        if var == "L":
            end = pd.Timestamp(int(p.day_ns[-1]))
            audit[pair] = {"d1_bars": len(d1), "first": str(pd.Timestamp(int(p.day_ns[0])).date()),
                           "last": str(end.date()), "median_m1_per_bar": float(d1["n_m1"].median()),
                           "bars_lt_600_m1": int((d1["n_m1"] < 600).sum())}
            # real-data parity: cycle 12 engine in runner-fill mode == locked cycle 4B runner
            mine = c12.run(p, "L", *DEV, fill="runner")
            bars = d1.assign(ts_utc=p.day_ns)
            ref = pd.DataFrame(run_rsi2_oos_batch(RSI2EngineConfig("x", pair, 1), bars,
                                                  [Fold(0, 0, 0, *DEV)])[0].trades)
            audit[pair]["parity_with_4b_runner"] = bool(
                len(mine) == len(ref)
                and np.array_equal(mine["ts_entry_ns"].to_numpy(), ref["ts_entry_ns"].to_numpy())
                and np.allclose(mine["pnl_r"].to_numpy(), ref["pnl_r"].to_numpy(), atol=1e-12))
        t = c12.run(p, var, *DEV)
        t.to_csv(OUT / "trades" / f"{pair}_{var}_dev.csv", index=False)
        r = t["pnl_r"].to_numpy()
        stress = r - t["spread_r"].to_numpy()
        rep = evaluate_secondary(t, cost_stress_pf=stats(stress)["pf"], min_trade_count=25)
        luck = c12.luck_test(t, c12.outcome_table(p, *DEV), SEED_BASE + k, N_PERMS)
        row = {"slot_index": k, "pair": pair, "variant": var, "trades": len(t),
               "n_long": int((t["side"] == 1).sum()), "trades_per_year": len(t) / 7, **stats(r),
               "r2": rep.details["r2"], "G1": rep.G1_pass, "G2": rep.G2_pass,
               "G3_report_only": rep.G3_pass, "G4": rep.G4_pass, "G5": rep.G5_pass,
               "cost_stress_pf": rep.details["cost_stress_pf"], **luck,
               "luck_gate": luck["p_mean_r"] <= ALPHA}
        row["dev_pass"] = bool(row["G1"] and row["G2"] and row["G4"] and row["G5"] and row["luck_gate"])
        dev_rows.append(row)
        print(f"[c12] {pair} {var}: n={len(t)} PF={row['pf']:.2f} meanR={row['mean_r']:+.3f} "
              f"R2={row['r2']:.2f} p={luck['p_mean_r']:.4f} pass={row['dev_pass']}", flush=True)
        if not row["dev_pass"]:
            continue
        ho_end = int(p.day_ns[-1]) + 1
        th = c12.run(p, var, HO_START, ho_end)
        th.to_csv(OUT / "trades" / f"{pair}_{var}_holdout.csv", index=False)
        lh = c12.luck_test(th, c12.outcome_table(p, HO_START, ho_end), SEED_BASE + 500 + k, N_PERMS)
        h = {"pair": pair, "variant": var, "trades": len(th), **stats(th["pnl_r"].to_numpy()), **lh}
        h["holdout_pass"] = bool(h["pf"] >= 1.3 and h["win_rate"] >= 0.5 and h["max_dd_r"] < 10
                                 and h["p_mean_r"] <= ALPHA)
        ho_rows.append(h)
        print(f"[c12]   HOLDOUT {pair} {var}: n={len(th)} PF={h['pf']:.2f} p={lh['p_mean_r']:.4f} "
              f"pass={h['holdout_pass']}", flush=True)
    pd.DataFrame(dev_rows).to_csv(OUT / "dev_report.csv", index=False)
    pd.DataFrame(ho_rows).to_csv(OUT / "holdout_report.csv", index=False)
    (OUT / "data_audit.json").write_text(json.dumps(audit, indent=2), "utf-8")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({
        "git_head": head.stdout.strip(), "alpha": ALPHA, "n_perms": N_PERMS,
        "dev_pass": [f"{r['pair']}_{r['variant']}" for r in dev_rows if r["dev_pass"]],
        "holdout_pass": [f"{r['pair']}_{r['variant']}" for r in ho_rows if r["holdout_pass"]],
    }, indent=2), "utf-8")
    print(json.dumps(audit, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
