"""Cycle 20 (pre-reg 4d802da): Silver Bullet v5, 18 slots on 6 fresh markets, 2018 -> end. Writes out/c20/."""
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

from v17.data.parquet_store import read_bars  # noqa: E402
from v17.setups import c17_silver_bullet as base  # noqa: E402
from v17.setups import c20_silver_bullet_v5 as v5  # noqa: E402

OUT = REPO / "out" / "c20"
ALPHA = 0.05 / 18
START, END = "2018-01-01", "2026-12-31"


def load_m1(sym: str) -> pd.DataFrame:
    paired = REPO / "data" / "bars_m1_paired" / sym
    if paired.exists():
        return pd.read_parquet(paired)
    root = REPO / ".worktrees" / "sb-6-engine-gate" / "data"
    return pd.concat([read_bars(root=root, symbol=sym, partition=p, dev_only=p == "dev")
                      for p in ("dev", "holdout")], ignore_index=True)


def stats(r: np.ndarray) -> dict[str, float]:
    loss = -r[r < 0].sum()
    eq = np.r_[0.0, np.cumsum(r)]
    return {"trades": int(len(r)), "pf": float(r[r > 0].sum() / loss) if loss > 0 else float("nan"),
            "mean_r": float(r.mean()) if len(r) else float("nan"),
            "win_rate": float((r > 0).mean()) if len(r) else float("nan"),
            "max_dd_r": float((np.maximum.accumulate(eq) - eq).max())}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = {s: base.prepare(load_m1(s)) for s in set(v5.MARKETS) | {"USA500IDXUSD", "DOLLARIDXUSD"}}
    rows = []
    for k, (w, m) in enumerate(v5.slots()):
        b, pb = bars[m], bars[v5.PARTNER[m][0]]
        days = base.day_table(b, w, START, END)
        t = v5.run_slot_v5(b, days, m, w, pb)
        t.to_csv(OUT / f"trades_{w}_{m}.csv", index=False)
        st = stats(t["r"].to_numpy() if len(t) else np.array([]))
        lk = (base.luck_test(b, days, t, v5.SPECS[m], 20261118 * 1000 + 100 + k) if len(t) >= 2
              else {"p_mean_r": float("nan"), "null_mean_r_median": float("nan")})
        ln = t[t.side == 1].r if len(t) else pd.Series(dtype=float)
        sh = t[t.side == -1].r if len(t) else pd.Series(dtype=float)
        row = {"slot_index": k, "window": w, "market": m, **st, "p_mean_r": lk["p_mean_r"],
               "random_median": lk["null_mean_r_median"], "long_n": len(ln),
               "long_mean_r": float(ln.mean()) if len(ln) else float("nan"), "short_n": len(sh),
               "short_mean_r": float(sh.mean()) if len(sh) else float("nan"),
               "pass": bool(st["trades"] > 0 and st["pf"] >= 1.3 and lk["p_mean_r"] <= ALPHA)}
        rows.append(row)
        print(f"[c20] {w:3s} {m:12s} n={st['trades']:4d} PF={st['pf']:.2f} meanR={st['mean_r']:+.3f} "
              f"win={st['win_rate']:.2f} p={row['p_mean_r']:.4f} DD={st['max_dd_r']:.1f} "
              f"| L {row['long_n']} @ {row['long_mean_r']:+.2f} S {row['short_n']} @ {row['short_mean_r']:+.2f} "
              f"PASS={row['pass']}", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "report.csv", index=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    (OUT / "run_manifest.json").write_text(json.dumps({"git_head": head.stdout.strip(), "alpha": ALPHA,
        "passed": [f"{r['window']}_{r['market']}" for r in rows if r["pass"]]}, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
