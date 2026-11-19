"""Cycle 21 stage 3 (review round 3): REAL-DATA implementation parity, 2018-2024, Model A, SMT off.

Runs the main engine and the independent reference on the same frozen development data and configuration and
requires exact agreement on every XNYS date (outcome) and every trade field. Prints NO performance statistics
(those belong to stage 4, which may only start after exact parity). Any mismatch -> exit 1 and stop.

Writes out/c21/real_parity.md and out/c21/real_parity_trades_<instrument>.csv (main engine trade records).
"""

# ruff: noqa: E402
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from c21_reference_impl import RefMarket, run_day
from v17.smc_sb.config import BASELINE, INSTRUMENTS
from v17.smc_sb.data import build_market, load_m1
from v17.smc_sb.engine import Engine
from v17.smc_sb.session import xnys_dates

OUT = REPO / "out" / "c21"
START, END = "2018-01-01", "2024-12-31"
FIELDS = ["side", "ref", "sweep_ns", "mss_ns", "swing", "fvg_bottom", "fvg_top", "limit", "stop", "target_name",
          "target", "fill_ns", "exit_ns", "exit_reason", "exit_price", "gap_through", "data_gap", "r"]


def view(t: dict) -> dict:
    return {"side": t["side"], "ref": t["liquidity_ref"], "sweep_ns": pd.Timestamp(t["sweep_ts"]).value,
            "mss_ns": pd.Timestamp(t["mss_ts"]).value, "swing": t["mss_broken_swing"], "fvg_bottom": t["fvg_bottom"],
            "fvg_top": t["fvg_top"], "limit": t["limit"], "stop": t["stop"], "target_name": t["target_name"],
            "target": t["target"], "fill_ns": pd.Timestamp(t["fill_ts"]).value,
            "exit_ns": pd.Timestamp(t["exit_ts"]).value, "exit_reason": t["exit_reason"],
            "exit_price": t["exit_price"], "gap_through": bool(t["gap_through"]), "data_gap": bool(t["data_gap"]),
            "r": t["r"]}


def equal(a: object, b: object) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True)
    days = xnys_dates(START, END)
    lines = ["# Cycle 21 stage 3: real-data implementation parity (2018-2024, Model A, SMT off)", "",
             f"Git HEAD `{head.stdout.strip()}`, config fingerprint `{BASELINE.fingerprint()}`.",
             "No performance statistics are computed here (stage 4 only after exact parity).", "",
             "| instrument | XNYS dates | outcome mismatches | trades main | trades ref | field mismatches | max abs dR | result |",
             "|---|---|---|---|---|---|---|---|"]
    all_ok, outcome_counts = True, {}
    for name in INSTRUMENTS:
        m1 = load_m1(name)
        eng, ref = Engine(build_market(name, m1), BASELINE), RefMarket(m1, name)
        bad_outcome, bad_field, trades, max_dr, n_ref = [], [], [], 0.0, 0
        counts: dict[str, int] = {}
        for d in days:
            a = eng.run_day(d)
            r_reason, r_trade = run_day(ref, d, model="A")
            counts[a.reason] = counts.get(a.reason, 0) + 1
            n_ref += r_trade is not None
            if a.reason != r_reason:
                bad_outcome.append((d.isoformat(), a.reason, r_reason))
                continue
            if a.trade is None:
                continue
            trades.append(a.trade)
            v = view(a.trade)
            diff = [f for f in FIELDS if not equal(v[f], r_trade[f])]
            max_dr = max(max_dr, abs(v["r"] - r_trade["r"]))
            if diff:
                bad_field.append((d.isoformat(), diff))
        ok = not bad_outcome and not bad_field
        all_ok &= ok
        outcome_counts[name] = counts
        pd.DataFrame(trades).to_csv(OUT / f"real_parity_trades_{name}.csv", index=False)
        lines.append(f"| {name} | {len(days)} | {len(bad_outcome)} | {len(trades)} | {n_ref} | {len(bad_field)} | "
                     f"{max_dr:.1e} | {'MATCH' if ok else 'MISMATCH - STOP'} |")
        print(lines[-1], flush=True)
        for x in bad_outcome[:20]:
            lines.append(f"- outcome mismatch {x}")
        for x in bad_field[:20]:
            lines.append(f"- field mismatch {x}")
    lines += ["", "## Day outcomes (main engine)", "", "```", json.dumps(outcome_counts, indent=1), "```", "",
              f"**Overall: {'MATCH - stage 4 may start' if all_ok else 'MISMATCH - process stopped'}**", ""]
    (OUT / "real_parity.md").write_text("\n".join(lines), "utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
