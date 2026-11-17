"""Cycle 16 (pre-reg in docs/superpowers/specs/2026-11-17-cycle16-ibs-fx-prereg.md): IBS long+short on FX majors."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.setups import c15_ibs as ibs  # noqa: E402
from v17.setups.c12_rsi2_fx import luck_test  # noqa: E402

sys.path.insert(0, str(REPO / "scripts"))
from run_c15_ibs import ftmo_sim, stats  # noqa: E402

OUT = REPO / "out" / "c16"
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD")
TUNE = (pd.Timestamp("2015-06-01").value, pd.Timestamp("2022-01-01").value)
RECENT = (pd.Timestamp("2022-01-01").value, pd.Timestamp("2100-01-01").value)
ALPHA = 0.05 / 7
RISK_PER_R = 0.5


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    preps = {p: ibs.prepare(pd.read_parquet(REPO / "data" / "bars_d1_fxny" / p / "d1.parquet")) for p in PAIRS}
    rows = []
    for k, s in enumerate(ibs.MENU):
        edges = []
        for p in PAIRS:
            t = ibs.run(preps[p], s, *TUNE)
            lt = luck_test(t, ibs.outcome_table(preps[p], s, *TUNE), 20261117 * 1000 + 900 + k, 2_000)
            edges.append(lt["observed_mean_r"] - lt["null_mean_r_median"])
        rows.append({"setting_index": k, "lo": s.lo, "hi": s.hi, "exit": s.exit, "score": float(np.mean(edges)),
                     **{f"{p}_edge": e for p, e in zip(PAIRS, edges, strict=True)}})
        print(f"[c16-tune] {k}: lo={s.lo} hi={s.hi} exit={s.exit} score={rows[-1]['score']:+.4f}", flush=True)
    tune = pd.DataFrame(rows)
    tune.to_csv(OUT / "tuning.csv", index=False)
    win = ibs.MENU[int(tune["score"].idxmax())]
    print(f"[c16-tune] WINNER {win}", flush=True)

    ex, daily, passed = [], {}, []
    days = None
    for pi, p in enumerate(PAIRS):
        prep = preps[p]
        t = ibs.run(prep, win, *RECENT)
        t.to_csv(OUT / f"trades_{p}_recent.csv", index=False)
        lt = luck_test(t, ibs.outcome_table(prep, win, *RECENT), 20261117 * 1000 + 950 + pi, 10_000)
        st = stats(t["pnl_r"].to_numpy())
        lng, sht = t[t.side == 1].pnl_r, t[t.side == -1].pnl_r
        row = {"pair": p, **st, "p_mean_r": lt["p_mean_r"], "random_same_mix_median": lt["null_mean_r_median"],
               "long_trades": len(lng), "long_mean_r": float(lng.mean()), "short_trades": len(sht),
               "short_mean_r": float(sht.mean()), "pass": bool(st["pf"] >= 1.3 and lt["p_mean_r"] <= ALPHA)}
        ex.append(row)
        print(f"[c16] {p}: n={st['trades']} PF={st['pf']:.2f} meanR={st['mean_r']:+.3f} vs random "
              f"{lt['null_mean_r_median']:+.3f} p={lt['p_mean_r']:.4f} DD={st['max_dd_r']:.1f} | long {len(lng)} @ "
              f"{row['long_mean_r']:+.3f} short {len(sht)} @ {row['short_mean_r']:+.3f} PASS={row['pass']}", flush=True)
        daily[p] = (pd.Series(t["pnl_r"].to_numpy() * RISK_PER_R, index=pd.to_datetime(t["exit_day_ns"], unit="ns"))
                    .groupby(level=0).sum())
        d = pd.DatetimeIndex(pd.to_datetime(prep.day_ns[prep.day_ns >= RECENT[0]], unit="ns"))
        days = d if days is None else days.union(d)
        if row["pass"]:
            passed.append(p)
    pd.DataFrame(ex).to_csv(OUT / "exam_recent.csv", index=False)
    sims = {p: ftmo_sim(daily[p], days) for p in passed}
    if len(passed) > 1:
        sims["combined"] = ftmo_sim(pd.concat([daily[p] for p in passed]).groupby(level=0).sum(), days)
    (OUT / "ftmo_sim.json").write_text(json.dumps(sims, indent=2), "utf-8")
    print("[c16] passing pairs:", passed or "none", "| FTMO sim:", json.dumps(sims), flush=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({"git_head": head.stdout.strip(), "alpha": ALPHA,
                                                       "winner": win.__dict__, "passed": passed}), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
