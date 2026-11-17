"""Cycle 18b (pre-reg 273a09e): SB v3 + swing stop, ONE shot on holdout 2025 -> end. Writes out/c18b/."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c17_silver_bullet import load, stats  # noqa: E402
from v17.setups import c17_silver_bullet as sb  # noqa: E402

OUT = REPO / "out" / "c18b"
ALPHA = 0.05 / 12


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = {s: load(s) for s in sb.SYMBOLS}
    rows = []
    for k, (w, s) in enumerate(sb.slots()):
        b, sp = bars[s], sb.SPECS[s]
        days = sb.day_table(b, w, "2025-01-01", "2026-12-31")
        t = sb.run_slot_v3(b, days, sp, s, stop_mode="swing")
        t.to_csv(OUT / f"trades_{w}_{s}_holdout.csv", index=False)
        st = stats(t["r"].to_numpy())
        lk = sb.luck_test(b, days, t, sp, 20261117 * 1000 + 1200 + k)
        ln, sh = t[t.side == 1].r, t[t.side == -1].r
        rc = t.reason.value_counts().to_dict()
        row = {"window": w, "symbol": s, **st, "p_mean_r": lk["p_mean_r"], "random_median": lk["null_mean_r_median"],
               "long_n": len(ln), "long_mean_r": float(ln.mean()), "short_n": len(sh), "short_mean_r": float(sh.mean()),
               "sl": rc.get(1, 0), "tp": rc.get(2, 0), "time": rc.get(3, 0),
               "pass": bool(st["pf"] >= 1.3 and lk["p_mean_r"] <= ALPHA)}
        rows.append(row)
        print(f"[c18b] {w:3s} {s:13s} n={st['trades']:4d} PF={st['pf']:.2f} meanR={st['mean_r']:+.3f} "
              f"vs random {lk['null_mean_r_median']:+.3f} p={lk['p_mean_r']:.4f} DD={st['max_dd_r']:.1f} "
              f"| L {len(ln)} @ {row['long_mean_r']:+.2f} S {len(sh)} @ {row['short_mean_r']:+.2f} "
              f"| SL/TP/T {row['sl']}/{row['tp']}/{row['time']} PASS={row['pass']}", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "holdout_report.csv", index=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({"git_head": head.stdout.strip(), "alpha": ALPHA,
        "passed": [f"{r['window']}_{r['symbol']}" for r in rows if r["pass"]]}, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
