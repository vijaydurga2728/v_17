"""Cycle 19 (pre-reg c4461e8): SB v4 full ICT sequence. Exam 2015-2017; extra EURUSD 2010-2014; info 2018->end."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c17_silver_bullet import load, stats  # noqa: E402
from v17.setups import c17_silver_bullet as sb  # noqa: E402

OUT = REPO / "out" / "c19"
ALPHA = 0.05 / 12
PERIODS = {"exam_2015_2017": ("2015-01-01", "2017-12-31"), "info_2018_now": ("2018-01-01", "2026-12-31")}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = {s: load(s) for s in sb.SYMBOLS}
    rows = []
    for k, (w, s) in enumerate(sb.slots()):
        b, sp = bars[s], sb.SPECS[s]
        for pname, (a, z) in PERIODS.items():
            days = sb.day_table(b, w, a, z)
            t = sb.run_slot_v4(b, days, sp, s)
            t.to_csv(OUT / f"trades_{w}_{s}_{pname}.csv", index=False)
            st = stats(t["r"].to_numpy() if len(t) else np.array([]))
            lk = (sb.luck_test(b, days, t, sp, 20261117 * 1000 + 1300 + k) if pname.startswith("exam") and len(t) >= 2
                  else {"p_mean_r": float("nan"), "null_mean_r_median": float("nan")})
            row = {"window": w, "symbol": s, "period": pname, **st, "p_mean_r": lk["p_mean_r"],
                   "random_median": lk["null_mean_r_median"],
                   "pass": bool(pname.startswith("exam") and st["trades"] > 0 and st["pf"] >= 1.3
                                and lk["p_mean_r"] <= ALPHA)}
            rows.append(row)
            print(f"[c19] {pname:14s} {w:3s} {s:13s} n={st['trades']:4d} PF={st['pf']:.2f} "
                  f"meanR={st['mean_r']:+.3f} win={st['win_rate']:.2f} p={row['p_mean_r']:.4f} "
                  f"PASS={row['pass']}", flush=True)
    eu = bars["EURUSD"]
    for w in sb.WINDOWS:
        t = sb.run_slot_v4(eu, sb.day_table(eu, w, "2010-01-01", "2014-12-31"), sb.SPECS["EURUSD"], "EURUSD")
        st = stats(t["r"].to_numpy() if len(t) else np.array([]))
        rows.append({"window": w, "symbol": "EURUSD", "period": "extra_2010_2014", **st})
        print(f"[c19] extra_2010_2014 {w:3s} EURUSD        n={st['trades']:4d} PF={st['pf']:.2f} "
              f"meanR={st['mean_r']:+.3f}", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "report.csv", index=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({"git_head": head.stdout.strip(), "alpha": ALPHA,
        "passed": [f"{r['window']}_{r['symbol']}" for r in rows if r.get("pass")]}, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
