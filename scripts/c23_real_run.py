"""Cycle 23 spec §8 real-data sequence (user-approved 2026-11-19): DEV 2018-2024 only, Model A, SMT off.

Step 1  event-level parity, engine vs independent reference, every XNYS date, all 3 instruments. Any mismatch -> STOP
        (exit 1, no performance numbers).
Step 2  ledger + metrics + disagreement report (out/c23/real/).
Step 3  performance per instrument against the UNCHANGED c21 R26 gates:
        net PF >= 1.30, >= 100 trades, mean net R > 0, doubled-cost PF >= 1.10 (R23: spread x2 around mid,
        slippage 1.0), matched-control p <= 0.05/3 (R24 §3a, 5000 perms). The luck test is only run when every other
        gate passes (it cannot rescue a failed gate). Max DD, R^2 and annual results reported, not gated.
Charts are rendered separately: python scripts/c23_real_run.py --charts-only
The 2012-2014 holdout is never loaded (load_m1 raises on final_exam access).
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from c21_reference_impl import RefMarket, run_day

from v17.c23_visual.chart_manifest import generate as render_charts
from v17.c23_visual.event_export import data_fingerprint, export
from v17.c23_visual.metrics import candidate_metrics
from v17.c23_visual.parity import compare, engine_stream, reference_stream
from v17.c23_visual.report import DayRow, frame, markdown, row
from v17.smc_sb.config import ALPHA_PER_INSTRUMENT, BASELINE, INSTRUMENTS
from v17.smc_sb.data import DataIntegrityError, build_market, load_m1, widen_costs
from v17.smc_sb.engine import Engine, summarize
from v17.smc_sb.matched_random import matched_control_test
from v17.smc_sb.session import xnys_dates

OUT = REPO / "out" / "c23" / "real"
START, END = "2018-01-01", "2024-12-31"
DOUBLED = dataclasses.replace(BASELINE, cost_multiplier=2.0)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def parity_and_ledger(days: list) -> tuple[bool, dict[str, pd.DataFrame], list[DayRow]]:
    rows: list[DayRow] = []
    trades: dict[str, pd.DataFrame] = {}
    ok_all = True
    for name in INSTRUMENTS:
        log(f"{name}: loading dev M1")
        m1 = load_m1(name)
        mk = build_market(name, m1)
        rm = RefMarket(m1, name)
        records, ledger, raw = export(mk, BASELINE, days)
        by_day: dict[str, list] = {}
        for e in ledger:
            by_day.setdefault(e.trading_date, []).append(e)
        n_bad = 0
        for rec, res in zip(records, raw, strict=True):
            evs = by_day.get(rec.trading_date, [])
            tr: list[tuple] = []
            ref_reason, _ = run_day(rm, res.day, model="A", trace=tr)
            bad = compare(engine_stream(evs, rec.result), reference_stream(tr, ref_reason))
            n_bad += bool(bad)
            r = float(res.trade["r"]) if res.trade else math.nan  # type: ignore[arg-type]
            rows.append(row(rec, "A", ref_reason, bad, r, candidate_metrics(mk, evs)))
        ok_all &= n_bad == 0
        trades[name] = pd.DataFrame([r.trade for r in raw if r.trade is not None])
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / f"ledger_{name}.jsonl").open("w", encoding="utf-8") as fh:
            for e in ledger:
                fh.write(e.model_dump_json() + "\n")
        with (OUT / f"days_{name}.jsonl").open("w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(rec.model_dump_json() + "\n")
        trades[name].to_csv(OUT / f"trades_{name}.csv", index=False)
        log(f"{name}: {len(records)} dates, {len(trades[name])} trades, event mismatches {n_bad}")
    df = frame(rows)
    df.to_csv(OUT / "event_parity_real.csv", index=False)
    (OUT / "event_parity_real.md").write_text(
        markdown(
            df, f"Cycle 23 real-data event parity + metrics (dev {START}..{END}, Model A, SMT off)"
        ),
        encoding="utf-8",
    )
    return ok_all, trades, rows


def annual(tr: pd.DataFrame) -> list[str]:
    out = ["| year | trades | total R | PF |", "|---|---|---|---|"]
    for y, g in tr.groupby(tr.trading_date.str[:4]):
        s = summarize(g.r.to_numpy(float))
        out.append(f"| {y} | {s['trades']} | {s['total_r']:.2f} | {s['pf']:.2f} |")
    return out


def performance(days: list, trades: dict[str, pd.DataFrame]) -> list[str]:
    lines = [
        "| instrument | trades | net PF | mean R | doubled-cost PF | luck p | max DD (R) | R^2 | gates | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    detail: list[str] = []
    for name, tr in trades.items():
        s = summarize(tr.r.to_numpy(float)) if len(tr) else {"trades": 0}
        n = int(s["trades"])
        pf = float(s.get("pf", math.nan))
        mean_r = float(s.get("expectancy_r", math.nan))
        pf2, tr2, cost_note = math.nan, pd.DataFrame(), ""
        if n >= 100:  # the cost stress cannot rescue a failed trade-count gate
            log(f"{name}: doubled-cost run")
            try:
                m1w = widen_costs(load_m1(name), 2.0)
                tr2, _, _ = Engine(build_market(name, m1w), DOUBLED).run(days)
                pf2 = (
                    float(summarize(tr2.r.to_numpy(float)).get("pf", math.nan))
                    if len(tr2)
                    else math.nan
                )
            except DataIntegrityError as exc:  # known c21 widen_costs defect, recorded not hidden
                cost_note = f"doubled-cost run failed: {exc}"
        else:
            cost_note = "doubled-cost run not run: trade-count gate already failed"
        gates = {
            "PF>=1.30": pf >= 1.30,
            "trades>=100": n >= 100,
            "meanR>0": mean_r > 0,
            "2xcostPF>=1.10": pf2 >= 1.10,
        }
        p = math.nan
        if all(gates.values()):
            log(f"{name}: matched-control luck test (5000 perms)")
            mk = build_market(name, load_m1(name))
            p = float(matched_control_test(mk, tr, days, BASELINE)["p_one_sided"])
            gates["luck p<=0.0167"] = p <= ALPHA_PER_INSTRUMENT
        else:
            gates["luck p<=0.0167"] = False  # not run: an earlier gate already failed
        verdict = "PASS" if all(gates.values()) else "FAIL"
        failed = [k for k, v in gates.items() if not v]
        p_txt = "not run" if math.isnan(p) else f"{p:.4f}"
        lines.append(
            f"| {name} | {n} | {pf:.3f} | {mean_r:+.3f} | {pf2:.3f} | {p_txt} | "
            f"{s.get('max_dd_r', math.nan):.1f} | {s.get('equity_r2', math.nan):.2f} | "
            f"{'all' if not failed else 'failed: ' + ', '.join(failed)} | **{verdict}** |"
        )
        log(lines[-1])
        if cost_note:
            detail += ["", f"- {name}: {cost_note}"]
        if len(tr):
            wr = float(s.get("win_rate", math.nan))
            exits = tr.exit_reason.value_counts().to_dict()
            detail += [
                "",
                f"### {name}",
                "",
                f"Win rate {wr:.1%}, total R {s['total_r']:.2f}, exits {exits}, doubled-cost trades {len(tr2)}.",
                "",
                *annual(tr),
            ]
    return lines + detail


def charts_only(days: list) -> None:
    for name in INSTRUMENTS:
        log(f"{name}: charts")
        mk = build_market(name, load_m1(name))
        records, ledger, _ = export(mk, BASELINE, days)
        man = render_charts(mk, BASELINE, records, ledger, OUT / "charts", data_fingerprint(mk))
        log(f"{name}: charts {len(man['charts'])} failures {len(man['failures'])}")  # type: ignore[arg-type]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--charts-only", action="store_true")
    args = ap.parse_args()
    days = xnys_dates(START, END)
    if args.charts_only:
        charts_only(days)
        return 0
    ok, trades, _ = parity_and_ledger(days)
    md = [
        "# Cycle 23 real-data run (dev 2018-2024, Model A, SMT off)",
        "",
        f"Git `{head()}`, config `{BASELINE.fingerprint()}`, holdout 2012-2014 not loaded.",
        "",
        f"## Step 1: event parity — **{'MATCH' if ok else 'MISMATCH: STOPPED'}**",
        "",
        "Details: `event_parity_real.md`.",
        "",
    ]
    if ok:
        md += [
            "## Step 3: R26 performance gates (unchanged)",
            "",
            *performance(days, trades),
        ]
    (OUT / "c23_real_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    json.dump({"parity_ok": ok}, (OUT / "status.json").open("w"))
    log("done" if ok else "STOPPED on parity mismatch")
    return 0 if ok else 1


if __name__ == "__main__":
    np.seterr(all="ignore")
    raise SystemExit(main())
