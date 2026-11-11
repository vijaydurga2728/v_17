"""30-day demo weekly-review report.

Reads out/demo/trade_log.jsonl + equity_curve.jsonl. Prints:
  days elapsed since first poll
  trades opened, trades closed
  cumulative pnl_r, PF, WR, avg_r, max_dd_r
  dev-baseline comparison flags
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


DEV_AVG_R = 0.7445  # observed from cycle-4B dev scheme-1 run


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    trade_log = repo / "out" / "demo" / "trade_log.jsonl"
    equity_log = repo / "out" / "demo" / "equity_curve.jsonl"

    if not trade_log.exists():
        rows = []
    else:
        rows = [json.loads(l) for l in trade_log.read_text(encoding="utf-8").splitlines() if l.strip()]
    entries = [r for r in rows if r.get("event") == "entry"]
    exits = [r for r in rows if r.get("event") == "exit"]

    if equity_log.exists():
        poll_rows = [json.loads(l) for l in equity_log.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        poll_rows = []

    first_poll_date = poll_rows[0]["poll_date_utc"][:10] if poll_rows else "n/a"
    last_poll_date = poll_rows[-1]["poll_date_utc"][:10] if poll_rows else "n/a"
    days_elapsed = len(poll_rows)

    print(f"=== 30-day demo report ===")
    print(f"First poll: {first_poll_date}   Last poll: {last_poll_date}")
    print(f"Poll days recorded: {days_elapsed}")
    print(f"Entries: {len(entries)}   Exits: {len(exits)}")
    print(f"Days until 30-day review: {max(0, 30 - days_elapsed)}")

    if not exits:
        print("No closed trades yet. Need >= 1 to compute stats.")
        return 0

    pnl = np.array([float(e["pnl_r"]) for e in exits])
    wr = float((pnl > 0).mean())
    avg_r = float(pnl.mean())
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    pf = float(wins / losses) if losses > 0 else float("inf")
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(dd.max())

    print()
    print(f"Closed-trade stats ({len(exits)} trades):")
    print(f"  PF      = {pf:.3f}   (dev baseline PF=2.507)")
    print(f"  WR      = {wr:.1%}   (dev baseline WR=72.6%)")
    print(f"  avg_r   = {avg_r:+.4f}   (dev baseline avg_r=+{DEV_AVG_R:.4f})")
    print(f"  max_dd  = {max_dd:.2f} R")

    # Discrepancy flags
    flags = []
    if len(exits) >= 3:
        if avg_r < DEV_AVG_R * 0.5:
            flags.append("avg_r is <50% of dev baseline — possible live regime shift or infra mismatch")
        if avg_r > DEV_AVG_R * 2.0:
            flags.append("avg_r is >200% of dev baseline — unusual, check for logging bug")
    if flags:
        print()
        print("Flags:")
        for f in flags:
            print(f"  - {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
