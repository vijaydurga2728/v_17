"""Cycle 13: Connors RSI(2) as published (close > SMA200) on NAS100, SPX, US30 (pre-reg f13f19d)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.data.parquet_store import read_bars  # noqa: E402
from v17.setups import c12_rsi2_fx as eng  # noqa: E402
from v17.validation.secondary_gates import evaluate_secondary  # noqa: E402

OUT = REPO / "out" / "c13"
CACHE = REPO / "data" / "bars_d1_ny17"
MARKETS = ("USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD")
DEV = (pd.Timestamp("2018-01-01").value, pd.Timestamp("2025-01-01").value)
HO_START = pd.Timestamp("2025-01-01").value
ALPHA = 0.05 / 3
N_PERMS = 10_000
SEED = 20261117 * 1_000 + 300


def load_m1(sym: str) -> pd.DataFrame:
    if sym == "USATECHIDXUSD":
        root = REPO / ".worktrees" / "sb-6-engine-gate" / "data"
        m1 = pd.concat([read_bars(root=root, symbol=sym, partition=p, dev_only=p == "dev")
                        for p in ("dev", "holdout")], ignore_index=True)
    else:
        m1 = pd.read_parquet(REPO / "data" / "bars_m1_paired" / sym)
    return m1.drop_duplicates("ts_utc").sort_values("ts_utc")


def load_d1(sym: str) -> pd.DataFrame:
    f = CACHE / sym / "d1.parquet"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        eng.build_fxny_d1(load_m1(sym)).to_parquet(f, index=False)
    return pd.read_parquet(f)


def stats(r: np.ndarray) -> dict[str, float]:
    loss = -r[r < 0].sum()
    eq = np.r_[0.0, np.cumsum(r)]
    return {"pf": float(r[r > 0].sum() / loss) if loss > 0 else float("inf"),
            "mean_r": float(r.mean()) if len(r) else 0.0,
            "win_rate": float((r > 0).mean()) if len(r) else 0.0,
            "max_dd_r": float((np.maximum.accumulate(eq) - eq).max())}


def hand_rows(p: eng.Prepared, t: pd.DataFrame, sym: str) -> list[str]:
    d = p.d1
    day = pd.to_datetime(d["day"]).dt.date
    rows = []
    for _, x in t.head(5).iterrows():
        i, e, j = int(x.signal_i), int(x.entry_i), int(x.exit_i)
        reason = "close>SMA5" if p.mid_c[j] > p.sma[j] else "10-day cap"
        rows.append(f"| {sym} | {day[i]} | {p.mid_c[i]:.1f} | {p.sma200[i]:.1f} | {p.rsi[i]:.2f} | {day[e]} | "
                    f"{d.at[e, 'ask_o']:.1f} | {day[j]} | {d.at[j, 'bid_c']:.1f} | {reason} | {x.pnl_r:+.3f} |")
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "trades").mkdir(exist_ok=True)
    dev_rows, ho_rows = [], []
    hand = ["| Market | Signal day | Close | SMA200 | RSI(2) | Entry day | Entry (ask open) | Exit day | "
            "Exit (bid close) | Exit reason | R |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, sym in enumerate(MARKETS):
        d1 = load_d1(sym)
        p = eng.prepare(d1)
        t = eng.run(p, "L", *DEV, trend_filter=True)
        t.to_csv(OUT / "trades" / f"{sym}_dev.csv", index=False)
        hand += hand_rows(p, t, sym)
        r = t["pnl_r"].to_numpy()
        rep = evaluate_secondary(t, cost_stress_pf=stats(r - t["spread_r"].to_numpy())["pf"],
                                 min_trade_count=25)
        luck = eng.luck_test(t, eng.outcome_table(p, *DEV), SEED + k, N_PERMS)
        strict = eng.luck_test(t, eng.outcome_table(p, *DEV, trend_only=True), SEED + k, N_PERMS)
        unf = eng.run(p, "L", *DEV)
        row = {"market": sym, "d1_bars": len(d1), "trades": len(t), "trades_per_year": len(t) / 7,
               **stats(r), "r2": rep.details["r2"], "G1": rep.G1_pass, "G2": rep.G2_pass,
               "G3_report_only": rep.G3_pass, "G4": rep.G4_pass, "G5": rep.G5_pass,
               "cost_stress_pf": rep.details["cost_stress_pf"],
               "p_mean_r": luck["p_mean_r"], "null_mean_r_median": luck["null_mean_r_median"],
               "strict_null_p_report_only": strict["p_mean_r"],
               "strict_null_median_report_only": strict["null_mean_r_median"],
               "unfiltered_trades_report_only": len(unf),
               "unfiltered_pf_report_only": stats(unf["pnl_r"].to_numpy())["pf"],
               "luck_gate": luck["p_mean_r"] <= ALPHA}
        row["dev_pass"] = bool(row["G1"] and row["G2"] and row["G4"] and row["G5"] and row["luck_gate"])
        dev_rows.append(row)
        yr = t.assign(y=pd.to_datetime(t.ts_entry_ns, unit="ns").dt.year).groupby("y").pnl_r.sum().round(1)
        print(f"[c13] {sym}: n={len(t)} PF={row['pf']:.2f} meanR={row['mean_r']:+.3f} DD={row['max_dd_r']:.1f} "
              f"R2={row['r2']:.2f} p={row['p_mean_r']:.4f} (strict {row['strict_null_p_report_only']:.4f}) "
              f"pass={row['dev_pass']} | by year {yr.to_dict()}", flush=True)
        if not row["dev_pass"]:
            continue
        end = int(p.day_ns[-1]) + 1
        th = eng.run(p, "L", HO_START, end, trend_filter=True)
        th.to_csv(OUT / "trades" / f"{sym}_holdout.csv", index=False)
        lh = eng.luck_test(th, eng.outcome_table(p, HO_START, end), SEED + 500 + k, N_PERMS)
        h = {"market": sym, "trades": len(th), **stats(th["pnl_r"].to_numpy()), "p_mean_r": lh["p_mean_r"]}
        h["holdout_pass"] = bool(h["pf"] >= 1.3 and h["win_rate"] >= 0.5 and h["max_dd_r"] < 10
                                 and h["p_mean_r"] <= ALPHA)
        ho_rows.append(h)
        print(f"[c13]   HOLDOUT {sym}: n={len(th)} PF={h['pf']:.2f} WR={h['win_rate']:.2f} "
              f"DD={h['max_dd_r']:.1f} p={h['p_mean_r']:.4f} pass={h['holdout_pass']}", flush=True)
    pd.DataFrame(dev_rows).to_csv(OUT / "dev_report.csv", index=False)
    pd.DataFrame(ho_rows).to_csv(OUT / "holdout_report.csv", index=False)
    (OUT / "hand_check.md").write_text("# Cycle 13 hand-check (first 5 dev trades per market)\n\n"
                                       + "\n".join(hand) + "\n", "utf-8")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({
        "git_head": head.stdout.strip(), "alpha": ALPHA, "n_perms": N_PERMS,
        "dev_pass": [r["market"] for r in dev_rows if r["dev_pass"]],
        "holdout_pass": [r["market"] for r in ho_rows if r["holdout_pass"]]}, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
