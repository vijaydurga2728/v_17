"""Cycle 21 targeted-fixture parity (review round 3, section 3): run the main engine and the independent reference
on every fixture in `c21_fixtures.py`; require identical outcomes/trade fields AND the asserted behaviour.

Writes out/c21/fixture_parity.md. Exit code 0 only if every fixture passes both checks.
"""

# ruff: noqa: E402
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from c21_fixtures import DAY, Fixture, fixtures
from c21_reference_impl import RefMarket, run_day
from v17.smc_sb.config import BASELINE
from v17.smc_sb.data import build_market
from v17.smc_sb.engine import Engine

OUT = REPO / "out" / "c21"
FIELDS = ["side", "limit", "stop", "target", "exit_reason", "exit_price", "gap_through", "data_gap"]
XNYS = [d.date() for d in pd.bdate_range("2024-02-01", "2024-03-29")]


def hhmm(iso: str) -> str:
    return iso[11:16]


def check(f: Fixture) -> tuple[bool, str]:
    cfg = dataclasses.replace(BASELINE, entry_model=f.model, order_expiry=f.expiry)
    mk = build_market("NAS100", f.m1, xnys=XNYS, early_close=f.early)
    res = Engine(mk, cfg).run_day(DAY)
    ref_reason, ref_t = run_day(
        RefMarket(f.m1, "NAS100", xnys=XNYS, early=f.early), DAY, model=f.model, expiry=f.expiry
    )
    problems = []
    if res.reason != ref_reason:
        problems.append(f"outcome main={res.reason} ref={ref_reason}")
    if res.reason != f.expect_reason:
        problems.append(f"expected outcome {f.expect_reason}, got {res.reason}")
    t = res.trade
    if t is not None and ref_t is not None:
        for k in FIELDS:
            a, b = t[k], ref_t[k]
            if (abs(float(a) - float(b)) > 1e-9) if isinstance(a, float) else a != b:
                problems.append(f"parity {k}: main={a} ref={b}")
        if (
            pd.Timestamp(t["fill_ts"]).value != ref_t["fill_ns"]
            or pd.Timestamp(t["exit_ts"]).value != ref_t["exit_ns"]
        ):
            problems.append("parity fill/exit time")
        if abs(t["r"] - ref_t["r"]) > 1e-9:
            problems.append(f"parity r: {t['r']} vs {ref_t['r']}")
    for k, v in f.expect.items():
        if k == "rescan_reason":
            got = next((e.get("reason") for e in res.events if e["stage"] == "rescan_ended"), None)
        elif k == "exit_hhmm":
            got = hhmm(t["exit_ts"]) if t else None
        elif k == "fill_hhmm":
            got = hhmm(t["fill_ts"]) if t else None
        else:
            got = t.get(k) if t else None
        ok = (
            abs(float(got) - float(v)) < 1e-9
            if isinstance(v, float) and got is not None
            else got == v
        )
        if not ok:
            problems.append(f"expected {k}={v}, got {got}")
    detail = (
        f"{t['exit_reason']} @ {t['exit_price']:.4f} ({hhmm(t['exit_ts'])}), R {t['r']:+.4f}"
        if t
        else res.reason
    )
    return not problems, detail + ("" if not problems else " | " + "; ".join(problems))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [
        "# Cycle 21 targeted fixture parity (review round 3, section 3)",
        "",
        "Main engine vs independent reference on hand-designed synthetic days; each row must match exactly",
        "AND satisfy its required assertion.",
        "",
        "| fixture | requirement | model | expiry | result | detail |",
        "|---|---|---|---|---|---|",
    ]
    all_ok = True
    for f in fixtures():
        ok, detail = check(f)
        all_ok &= ok
        rows.append(
            f"| {f.name} | {f.requirement} | {f.model} | {f.expiry} | {'PASS' if ok else 'FAIL'} | {detail} |"
        )
        print(rows[-1], flush=True)
    rows += ["", f"**Overall: {'PASS' if all_ok else 'FAIL'}**", ""]
    (OUT / "fixture_parity.md").write_text("\n".join(rows), "utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
