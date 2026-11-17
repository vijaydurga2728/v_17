"""Cycle 15 (pre-reg a1588e1): IBS long+short. Tune 2016-2021, exams 1991-2011 and 2022-now. Writes out/c15/."""
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

OUT = REPO / "out" / "c15"
MARKETS = ("USATECHIDXUSD", "USA500IDXUSD")
DOCS = Path("C:/Users/Vijayakumar R/Documents")
FRESH_FILES = {"USATECHIDXUSD": "1990.11.06_2014.12.30", "USA500IDXUSD": "1989.12.31_2014.12.30"}
TUNE = (pd.Timestamp("2016-01-01").value, pd.Timestamp("2022-01-01").value)
FRESH = (pd.Timestamp("1991-09-01").value, pd.Timestamp("2011-09-01").value)
RECENT = (pd.Timestamp("2022-01-01").value, pd.Timestamp("2100-01-01").value)
COST_R_FRESH = 0.03
ALPHA = 0.05 / 4
RISK_PER_R = 0.5  # % of equity per 1R


def broker(sym: str) -> ibs.Prepared:
    return ibs.prepare(pd.read_parquet(REPO / "data" / "bars_d1_ny17" / sym / "d1.parquet"))


def fresh(sym: str) -> ibs.Prepared:
    rng = FRESH_FILES[sym]
    b = pd.read_csv(DOCS / f"{sym}_Daily_Bid_{rng}.csv")
    a = pd.read_csv(DOCS / f"{sym}_Daily_Ask_{rng}.csv")
    b.columns = ["t", "bid_o", "bid_h", "bid_l", "bid_c", "v"]
    a.columns = ["t", "ask_o", "ask_h", "ask_l", "ask_c", "v"]
    m = b.drop(columns="v").merge(a.drop(columns="v"), on="t", validate="one_to_one")
    m["day"] = pd.to_datetime(m["t"], format="%Y.%m.%d %H:%M:%S").dt.normalize()
    flat = (m.bid_o == m.bid_h) & (m.bid_h == m.bid_l) & (m.bid_l == m.bid_c)
    m = m[~flat & (m["day"] <= pd.Timestamp("2011-08-31"))].sort_values("day").reset_index(drop=True)
    return ibs.prepare(m)


def stats(r: np.ndarray) -> dict[str, float]:
    loss = -r[r < 0].sum()
    eq = np.r_[0.0, np.cumsum(r)]
    return {"trades": int(len(r)), "pf": float(r[r > 0].sum() / loss) if loss > 0 else float("inf"),
            "mean_r": float(r.mean()) if len(r) else 0.0,
            "win_rate": float((r > 0).mean()) if len(r) else 0.0,
            "max_dd_r": float((np.maximum.accumulate(eq) - eq).max())}


def step1() -> ibs.Setting:
    preps = {m: broker(m) for m in MARKETS}
    rows = []
    for k, s in enumerate(ibs.MENU):
        row: dict = {"setting_index": k, "lo": s.lo, "hi": s.hi, "exit": s.exit}
        edges = []
        for m in MARKETS:
            t = ibs.run(preps[m], s, *TUNE)
            lt = luck_test(t, ibs.outcome_table(preps[m], s, *TUNE), 20261117 * 1000 + 700 + k, 2_000)
            edge = lt["observed_mean_r"] - lt["null_mean_r_median"]
            edges.append(edge)
            row.update({f"{m}_trades": len(t), f"{m}_mean_r": lt["observed_mean_r"], f"{m}_edge": edge})
        row["score"] = float(np.mean(edges))
        rows.append(row)
        print(f"[c15-tune] {k}: lo={s.lo} hi={s.hi} exit={s.exit} score={row['score']:+.4f}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "tuning.csv", index=False)
    best = int(df["score"].idxmax())
    (OUT / "winner.json").write_text(json.dumps({"setting_index": best, **ibs.MENU[best].__dict__}), "utf-8")
    print(f"[c15-tune] WINNER {best}: {ibs.MENU[best]}", flush=True)
    return ibs.MENU[best]


def ftmo_sim(daily: pd.Series, days: pd.DatetimeIndex) -> dict[str, float]:
    pnl = daily.reindex(days, fill_value=0.0).to_numpy()
    out = {"pass": 0, "fail": 0, "unfinished": 0}
    days_to_pass = []
    for s in range(len(pnl)):
        cum = 0.0
        res = "unfinished"
        for k in range(s, len(pnl)):
            cum += pnl[k]
            if pnl[k] <= -5.0 or cum <= -10.0:
                res = "fail"
                break
            if cum >= 10.0:
                res = "pass"
                days_to_pass.append(k - s + 1)
                break
        out[res] += 1
    n = len(pnl)
    return {"start_days": n, "pass_share": out["pass"] / n, "fail_share": out["fail"] / n,
            "unfinished_share": out["unfinished"] / n,
            "median_trading_days_to_pass": float(np.median(days_to_pass)) if days_to_pass else float("nan")}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    win = step1()
    rows, recent_daily, passed = [], {}, []
    for mi, m in enumerate(MARKETS):
        ok_both = True
        for ei, (name, prep, w, cost) in enumerate([("fresh_1991_2011", fresh(m), FRESH, COST_R_FRESH),
                                                     ("recent_2022_now", broker(m), RECENT, 0.0)]):
            t = ibs.run(prep, win, *w)
            t["pnl_r"] = t["pnl_r"] - cost
            pool = ibs.outcome_table(prep, win, *w)
            pool[["r_long", "r_short"]] = pool[["r_long", "r_short"]] - cost
            t.to_csv(OUT / f"trades_{m}_{name}.csv", index=False)
            lt = luck_test(t, pool, 20261117 * 1000 + 800 + 2 * mi + ei, 10_000)
            st = stats(t["pnl_r"].to_numpy())
            lng, sht = t[t.side == 1].pnl_r.to_numpy(), t[t.side == -1].pnl_r.to_numpy()
            yr = t.assign(y=pd.to_datetime(t.ts_entry_ns, unit="ns").dt.year).groupby("y").pnl_r.sum()
            row = {"market": m, "exam": name, **st, "p_mean_r": lt["p_mean_r"],
                   "random_same_mix_median": lt["null_mean_r_median"],
                   "long_trades": len(lng), "long_mean_r": float(lng.mean()) if len(lng) else 0.0,
                   "short_trades": len(sht), "short_mean_r": float(sht.mean()) if len(sht) else 0.0,
                   "years_positive": int((yr > 0).sum()), "years": int(len(yr)),
                   "pass": bool(st["pf"] >= 1.3 and lt["p_mean_r"] <= ALPHA)}
            ok_both &= row["pass"]
            rows.append(row)
            print(f"[c15] {m[:6]} {name}: n={st['trades']} PF={st['pf']:.2f} meanR={st['mean_r']:+.3f} "
                  f"vs random {lt['null_mean_r_median']:+.3f} p={lt['p_mean_r']:.4f} DD={st['max_dd_r']:.1f} "
                  f"| long {len(lng)} @ {row['long_mean_r']:+.3f}, short {len(sht)} @ {row['short_mean_r']:+.3f} "
                  f"| yrs+ {row['years_positive']}/{row['years']} PASS={row['pass']}", flush=True)
            if name == "recent_2022_now":
                recent_daily[m] = (pd.Series(t["pnl_r"].to_numpy() * RISK_PER_R,
                                             index=pd.to_datetime(t["exit_day_ns"], unit="ns"))
                                   .groupby(level=0).sum())
                recent_days = pd.DatetimeIndex(pd.to_datetime(prep.day_ns[prep.day_ns >= RECENT[0]], unit="ns"))
        if ok_both:
            passed.append(m)
    pd.DataFrame(rows).to_csv(OUT / "exams.csv", index=False)
    sims = {m: ftmo_sim(recent_daily[m], recent_days) for m in passed}
    if len(passed) == 2:
        comb = pd.concat([recent_daily[m] for m in passed]).groupby(level=0).sum()
        sims["combined"] = ftmo_sim(comb, recent_days)
    (OUT / "ftmo_sim.json").write_text(json.dumps(sims, indent=2), "utf-8")
    print("[c15] markets passing both exams:", passed or "none", "| FTMO sim:", json.dumps(sims), flush=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({"git_head": head.stdout.strip(), "alpha": ALPHA,
                                                       "winner": win.__dict__, "passed": passed}), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
