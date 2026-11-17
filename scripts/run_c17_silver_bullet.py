"""Cycle 17 (pre-reg fad6564): Silver Bullet v2, 12 slots, dev gates then holdout for passers. Writes out/c17/."""
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
from v17.setups import c17_silver_bullet as sb  # noqa: E402

OUT = REPO / "out" / "c17"
ALPHA = 0.05 / 12
DEV = ("2018-01-01", "2024-12-31")
HOLDOUT = ("2025-01-01", "2026-12-31")


def load(sym: str) -> sb.Bars:
    if sym == "USA500IDXUSD":
        m1 = pd.read_parquet(REPO / "data" / "bars_m1_paired" / sym)
    else:
        root = REPO / ".worktrees" / "sb-6-engine-gate" / "data"
        m1 = pd.concat([read_bars(root=root, symbol=sym, partition=p, dev_only=p == "dev")
                        for p in ("dev", "holdout")], ignore_index=True)
    return sb.prepare(m1)


def stats(r: np.ndarray) -> dict[str, float]:
    loss = -r[r < 0].sum()
    eq = np.r_[0.0, np.cumsum(r)]
    return {"trades": int(len(r)), "pf": float(r[r > 0].sum() / loss) if loss > 0 else float("nan"),
            "mean_r": float(r.mean()) if len(r) else float("nan"),
            "win_rate": float((r > 0).mean()) if len(r) else float("nan"),
            "max_dd_r": float((np.maximum.accumulate(eq) - eq).max())}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = {s: load(s) for s in sb.SYMBOLS}
    rows, ho = [], []
    for k, (w, s) in enumerate(sb.slots()):
        b, sp = bars[s], sb.SPECS[s]
        days = sb.day_table(b, w, *DEV)
        t = sb.run_slot(b, days, sp)
        t.to_csv(OUT / f"trades_{w}_{s}_dev.csv", index=False)
        st = stats(t["r"].to_numpy()) if len(t) else stats(np.array([]))
        luck = sb.luck_test(b, days, t, sp, 20261117 * 1000 + 1000 + k) if len(t) >= 2 else {
            "observed_mean_r": float("nan"), "null_mean_r_median": float("nan"), "p_mean_r": 1.0}
        long_r, short_r = (t[t.side == 1].r, t[t.side == -1].r) if len(t) else (pd.Series([]), pd.Series([]))
        reasons = t["reason"].value_counts().to_dict() if len(t) else {}
        row = {"slot_index": k, "window": w, "symbol": s, "days": len(days), **st,
               "p_mean_r": luck["p_mean_r"], "random_median": luck["null_mean_r_median"],
               "long_n": len(long_r), "long_mean_r": float(long_r.mean()) if len(long_r) else float("nan"),
               "short_n": len(short_r), "short_mean_r": float(short_r.mean()) if len(short_r) else float("nan"),
               "sl": reasons.get(1, 0), "tp": reasons.get(2, 0), "time": reasons.get(3, 0)}
        row["dev_pass"] = bool(st["trades"] > 0 and st["pf"] >= 1.3 and luck["p_mean_r"] <= ALPHA)
        rows.append(row)
        print(f"[c17] {w:3s} {s:13s} n={st['trades']:4d} PF={st['pf']:.2f} meanR={st['mean_r']:+.3f} "
              f"vs random {luck['null_mean_r_median']:+.3f} p={luck['p_mean_r']:.4f} DD={st['max_dd_r']:.1f} "
              f"| L {row['long_n']} @ {row['long_mean_r']:+.2f} S {row['short_n']} @ {row['short_mean_r']:+.2f} "
              f"| SL/TP/T {row['sl']}/{row['tp']}/{row['time']} PASS={row['dev_pass']}", flush=True)
        if row["dev_pass"]:
            hd = sb.day_table(b, w, *HOLDOUT)
            th = sb.run_slot(b, hd, sp)
            th.to_csv(OUT / f"trades_{w}_{s}_holdout.csv", index=False)
            hs = stats(th["r"].to_numpy())
            ho.append({"window": w, "symbol": s, **hs, "holdout_pass": bool(hs["pf"] >= 1.2)})
            print(f"[c17]   HOLDOUT {w} {s}: n={hs['trades']} PF={hs['pf']:.2f} meanR={hs['mean_r']:+.3f} "
                  f"DD={hs['max_dd_r']:.1f} pass={hs['pf'] >= 1.2}", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "dev_report.csv", index=False)
    pd.DataFrame(ho).to_csv(OUT / "holdout_report.csv", index=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({
        "git_head": head.stdout.strip(), "alpha": ALPHA,
        "dev_pass": [f"{r['window']}_{r['symbol']}" for r in rows if r["dev_pass"]],
        "holdout_pass": [f"{r['window']}_{r['symbol']}" for r in ho if r["holdout_pass"]]}, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
