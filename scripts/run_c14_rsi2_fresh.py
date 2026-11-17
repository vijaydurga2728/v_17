"""Cycle 14 (pre-reg 6870410): tune RSI2 on 2016-2024, then ONE exam on untouched 1991-2011 data.

Step 1 finishes and the winner is written to disk before the 1990-2011 files are read.
"""
from __future__ import annotations

import json
import subprocess
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.setups import c12_rsi2_fx as eng  # noqa: E402

OUT = REPO / "out" / "c14"
MARKETS = ("USATECHIDXUSD", "USA500IDXUSD")
DOCS = Path("C:/Users/Vijayakumar R/Documents")
FRESH_FILES = {"USATECHIDXUSD": "1990.11.06_2014.12.30", "USA500IDXUSD": "1989.12.31_2014.12.30"}
TUNE = (pd.Timestamp("2016-01-01").value, pd.Timestamp("2025-01-01").value)
FRESH = (pd.Timestamp("1991-09-01").value, pd.Timestamp("2011-09-01").value)
FRESH_CUTOFF = pd.Timestamp("2011-08-31")
COST_R = 0.03  # 0.03% round trip / (R unit = 1% of price)
ALPHA = 0.05 / 6
MENU = [{"rsi_buy": b, "trend_filter": f, "exit_sma": x}
        for b, f, x in product((5.0, 10.0), (False, True), (5, 10))]


def stats(r: np.ndarray) -> dict[str, float]:
    loss = -r[r < 0].sum()
    eq = np.r_[0.0, np.cumsum(r)]
    return {"trades": len(r), "pf": float(r[r > 0].sum() / loss) if loss > 0 else float("inf"),
            "mean_r": float(r.mean()) if len(r) else 0.0,
            "win_rate": float((r > 0).mean()) if len(r) else 0.0,
            "max_dd_r": float((np.maximum.accumulate(eq) - eq).max())}


def step1_tune() -> dict:
    rows = []
    preps = {m: eng.prepare(pd.read_parquet(REPO / "data" / "bars_d1_ny17" / m / "d1.parquet")) for m in MARKETS}
    for k, s in enumerate(MENU):
        edges = []
        row = {"setting_index": k, **s}
        for m in MARKETS:
            p = preps[m]
            t = eng.run(p, "L", *TUNE, **s)
            if len(t) == 0:
                edges.append(-np.inf)
                row[f"{m}_trades"] = 0
                continue
            pool = eng.outcome_table(p, *TUNE, exit_sma=s["exit_sma"])
            lt = eng.luck_test(t, pool, 20261117 * 1000 + 400 + k, 2_000)
            edge = lt["observed_mean_r"] - lt["null_mean_r_median"]
            edges.append(edge)
            row.update({f"{m}_trades": len(t), f"{m}_mean_r": lt["observed_mean_r"],
                        f"{m}_null_median": lt["null_mean_r_median"], f"{m}_edge": edge})
        row["score"] = float(np.mean(edges))
        rows.append(row)
        print(f"[c14-tune] {k}: buy<{s['rsi_buy']:.0f} filter={s['trend_filter']} exit=SMA{s['exit_sma']} "
              f"score={row['score']:+.4f}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "tuning.csv", index=False)
    best = int(df["score"].idxmax())  # first max = lowest setting_index on ties
    winner = MENU[best]
    (OUT / "winner.json").write_text(json.dumps({"setting_index": best, **winner}, indent=2), "utf-8")
    print(f"[c14-tune] WINNER {best}: {winner}", flush=True)
    return winner


def load_fresh(sym: str) -> pd.DataFrame:
    rng = FRESH_FILES[sym]
    b = pd.read_csv(DOCS / f"{sym}_Daily_Bid_{rng}.csv")
    a = pd.read_csv(DOCS / f"{sym}_Daily_Ask_{rng}.csv")
    b.columns = ["t", "bid_o", "bid_h", "bid_l", "bid_c", "v"]
    a.columns = ["t", "ask_o", "ask_h", "ask_l", "ask_c", "v"]
    m = b.drop(columns="v").merge(a.drop(columns="v"), on="t", validate="one_to_one")
    m["day"] = pd.to_datetime(m["t"], format="%Y.%m.%d %H:%M:%S").dt.normalize()
    flat = (m.bid_o == m.bid_h) & (m.bid_h == m.bid_l) & (m.bid_l == m.bid_c)
    m = m[~flat & (m["day"] <= FRESH_CUTOFF)].sort_values("day").reset_index(drop=True)
    return m[["day", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]]


def step2_exam(winner: dict) -> list[dict]:
    cands = [("tuned_winner", winner),
             ("original", {"rsi_buy": 10.0, "trend_filter": False, "exit_sma": 5}),
             ("with_200d_filter", {"rsi_buy": 10.0, "trend_filter": True, "exit_sma": 5})]
    rows = []
    for mi, sym in enumerate(MARKETS):
        d1 = load_fresh(sym)
        p = eng.prepare(d1)
        print(f"[c14-exam] {sym}: {len(d1)} clean daily bars {d1.day.min().date()} -> {d1.day.max().date()}",
              flush=True)
        for ci, (name, s) in enumerate(cands):
            t = eng.run(p, "L", *FRESH, **s)
            t["pnl_r"] = t["pnl_r"] - COST_R
            t.to_csv(OUT / f"fresh_trades_{sym}_{name}.csv", index=False)
            pool = eng.outcome_table(p, *FRESH, exit_sma=s["exit_sma"])
            pool["r_long"] = pool["r_long"] - COST_R
            lt = eng.luck_test(t, pool, 20261117 * 1000 + 600 + 3 * mi + ci, 10_000)
            st = stats(t["pnl_r"].to_numpy())
            yr = t.assign(y=pd.to_datetime(t.ts_entry_ns, unit="ns").dt.year).groupby("y").pnl_r.sum()
            row = {"market": sym, "candidate": name, **s, **st, "p_mean_r": lt["p_mean_r"],
                   "null_mean_r_median": lt["null_mean_r_median"],
                   "years_positive": int((yr > 0).sum()), "years": int(len(yr)),
                   "pass": bool(st["pf"] >= 1.3 and lt["p_mean_r"] <= ALPHA)}
            rows.append(row)
            print(f"[c14-exam] {sym} {name}: n={st['trades']} PF={st['pf']:.2f} meanR={st['mean_r']:+.3f} "
                  f"vs random {lt['null_mean_r_median']:+.3f} p={lt['p_mean_r']:.4f} DD={st['max_dd_r']:.1f} "
                  f"yrs+ {row['years_positive']}/{row['years']} PASS={row['pass']}", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "fresh_exam.csv", index=False)
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    winner = step1_tune()
    rows = step2_exam(winner)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({
        "git_head": head.stdout.strip(), "alpha": ALPHA, "winner": winner,
        "passes": [f"{r['market']}:{r['candidate']}" for r in rows if r["pass"]]}, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
