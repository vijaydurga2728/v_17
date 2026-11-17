"""Cycle 11: RSI(2) cross-index replication on SPX and US30 (pre-reg 294e813).

Dev gates (cycle 4B standard + spread-cost check + mean-R luck test at alpha 0.025),
then holdout only for symbols that pass dev. Writes out/c11/.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import v17.backtest.rsi2_runner as rsi2_runner  # noqa: E402
from v17.backtest.rsi2_runner import run_rsi2_oos_batch  # noqa: E402
from v17.backtest.walkforward import Fold, generate_folds  # noqa: E402
from v17.data.parquet_store import read_bars_d1  # noqa: E402
from v17.setups.rsi2_engines import RSI2_CATALOG, RSI2EngineConfig  # noqa: E402
from v17.validation.mcpt_scheme1 import run_scheme1_mcpt_rsi2  # noqa: E402
from v17.validation.secondary_gates import evaluate_secondary  # noqa: E402

OUT = REPO / "out" / "c11"
SYMBOLS = ("USA500IDXUSD", "USA30IDXUSD")
N_PERMS = 10_000
ALPHA = 0.05 / 2
HO_START = pd.Timestamp("2025-01-01", tz="UTC").value
HO_END = pd.Timestamp("2026-10-15", tz="UTC").value  # data ends 2026-10-14


def trades_df(engine: RSI2EngineConfig, bars: pd.DataFrame, folds: list[Fold]) -> pd.DataFrame:
    rows = [t for log in run_rsi2_oos_batch(engine, bars, folds) for t in log.trades]
    return pd.DataFrame(rows).sort_values("ts_entry_ns").reset_index(drop=True) if rows else pd.DataFrame()


def pf(r: np.ndarray) -> float:
    loss = -r[r < 0].sum()
    return float(r[r > 0].sum() / loss) if loss > 0 else float("inf")


def max_dd(r: np.ndarray) -> float:
    eq = np.r_[0.0, np.cumsum(r)]
    return float((np.maximum.accumulate(eq) - eq).max())


def stress_pf(engine: RSI2EngineConfig, bars: pd.DataFrame, folds: list[Fold]) -> float:
    orig = rsi2_runner.COST_SLIPPAGE_PTS_USATECH
    rsi2_runner.COST_SLIPPAGE_PTS_USATECH = orig * 2
    try:
        return pf(trades_df(engine, bars, folds)["pnl_r"].to_numpy())
    finally:
        rsi2_runner.COST_SLIPPAGE_PTS_USATECH = orig


def median_spread(symbol: str) -> float:
    m1 = pd.read_parquet(REPO / "data" / "bars_m1_paired" / symbol, columns=["ts_utc", "bid_c", "ask_c"])
    m1 = m1[m1["ts_utc"] < HO_START]
    return float((m1["ask_c"] - m1["bid_c"]).median())


def luck_test(engine: RSI2EngineConfig, bars: pd.DataFrame, tr: pd.DataFrame, label: str,
              start: int, end: int) -> dict[str, float]:
    res = run_scheme1_mcpt_rsi2(engine_id=engine.engine_id, bars_d1=bars, observed_trades=tr,
                                window_label=label, window_start_ns=start, window_end_ns=end,
                                n_permutations=N_PERMS, out_root=OUT)
    null = pd.read_parquet(OUT / "mcpt_scheme1" / engine.engine_id / label / "null_distribution.parquet")
    nm = null["null_mean_r"].to_numpy()
    nm = nm[np.isfinite(nm)]
    p = (int((nm >= res.observed_mean_r).sum()) + 1) / (len(nm) + 1)
    return {"observed_mean_r": res.observed_mean_r, "null_mean_r_median": res.null_mean_r_median,
            "n_null": int(len(nm)), "p_mean_r": p, "p_pf_reported_only": res.p_pf}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    folds = generate_folds()
    dev_lo, dev_hi = min(f.oos_start for f in folds), max(f.oos_end for f in folds)
    man: dict = {"git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                                            text=True).stdout.strip(), "n_perms": N_PERMS, "alpha": ALPHA}
    dev_rows, ho_rows, all_tr = [], [], {}
    for sym in SYMBOLS:
        eng = RSI2EngineConfig(f"RSI2-{sym}", sym, 1)
        bars = read_bars_d1(sym, "dev")
        tr = trades_df(eng, bars, folds)
        tr.to_csv(OUT / f"trades_{sym}_dev.csv", index=False)
        r = tr["pnl_r"].to_numpy()
        rep = evaluate_secondary(tr, cost_stress_pf=stress_pf(eng, bars, folds), min_trade_count=25)
        spread = median_spread(sym)
        r_spread = r - spread / tr["r_dist"].to_numpy()
        luck = luck_test(eng, bars, tr, "dev", dev_lo, dev_hi)
        row = {"symbol": sym, "trades": len(tr), "trades_per_year": len(tr) / 7, "pf": pf(r),
               "mean_r": float(r.mean()), "win_rate": float((r > 0).mean()), "max_dd_r": max_dd(r),
               "G1": rep.G1_pass, "G2": rep.G2_pass, "G3_report_only": rep.G3_pass, "G4": rep.G4_pass,
               "G5": rep.G5_pass, "median_spread_pts": spread, "pf_after_spread": pf(r_spread),
               "spread_gate": pf(r_spread) >= 1.3, **luck, "luck_gate": luck["p_mean_r"] <= ALPHA}
        row["dev_pass"] = bool(row["G1"] and row["G2"] and row["G4"] and row["G5"]
                               and row["spread_gate"] and row["luck_gate"])
        dev_rows.append(row)
        print(f"[c11] DEV {sym}: n={row['trades']} PF={row['pf']:.2f} meanR={row['mean_r']:.3f} "
              f"p={row['p_mean_r']:.4f} pass={row['dev_pass']}", flush=True)
        if not row["dev_pass"]:
            continue
        hb = read_bars_d1(sym, "holdout")
        fold = Fold(100, 0, HO_START - 1, HO_START, HO_END)
        th = trades_df(eng, hb, [fold])
        th.to_csv(OUT / f"trades_{sym}_holdout.csv", index=False)
        all_tr[sym] = th
        rh = th["pnl_r"].to_numpy()
        lh = luck_test(eng, hb, th, "holdout", HO_START, HO_END)
        h = {"symbol": sym, "trades": len(th), "pf": pf(rh), "mean_r": float(rh.mean()),
             "win_rate": float((rh > 0).mean()), "max_dd_r": max_dd(rh), **lh}
        h["holdout_pass"] = bool(h["pf"] >= 1.3 and h["win_rate"] >= 0.5 and h["max_dd_r"] < 10
                                 and h["p_mean_r"] <= ALPHA)
        ho_rows.append(h)
        print(f"[c11] HOLDOUT {sym}: n={h['trades']} PF={h['pf']:.2f} p={h['p_mean_r']:.4f} "
              f"pass={h['holdout_pass']}", flush=True)
    pd.DataFrame(dev_rows).to_csv(OUT / "dev_report.csv", index=False)
    pd.DataFrame(ho_rows).to_csv(OUT / "holdout_report.csv", index=False)

    # Section 6: overlap with NAS100 and combined frequency (dev window, reporting only)
    nas = trades_df(RSI2_CATALOG[0], read_bars_d1("USATECHIDXUSD", "dev"), folds)
    nas_days = set(pd.to_datetime(nas["ts_entry_ns"], unit="ns").dt.date)
    ov = {}
    combined = [nas.assign(sym="NAS")]
    for sym in SYMBOLS:
        t = pd.read_csv(OUT / f"trades_{sym}_dev.csv")
        d = pd.to_datetime(t["ts_entry_ns"], unit="ns").dt.date
        ov[sym] = {"trades": len(t), "share_same_day_as_nas": float(d.isin(nas_days).mean())}
        combined.append(t.assign(sym=sym))
    c = pd.concat(combined).sort_values("ts_entry_ns")
    cr = c["pnl_r"].to_numpy()
    ov["combined_3_symbols_dev"] = {"trades": len(c), "trades_per_year": len(c) / 7, "pf": pf(cr),
                                    "mean_r": float(cr.mean()), "max_dd_r": max_dd(cr),
                                    "nas_alone_max_dd_r": max_dd(nas["pnl_r"].to_numpy())}
    (OUT / "overlap.json").write_text(json.dumps(ov, indent=2), "utf-8")
    man.update(dev=[{k: r[k] for k in ("symbol", "dev_pass")} for r in dev_rows],
               holdout=[{k: r[k] for k in ("symbol", "holdout_pass")} for r in ho_rows])
    (OUT / "run_manifest.json").write_text(json.dumps(man, indent=2, default=str), "utf-8")
    print(json.dumps(ov, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
