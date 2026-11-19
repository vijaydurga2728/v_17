"""Cycle 23 Phase 2 (gate 6): event-level parity engine vs independent reference + descriptive metric report.

SYNTHETIC DATA ONLY: the six c21 seeds (scripts/c21_synthetic.py) and the hand-built fixtures. No 2018-2024 market
data and no holdout access (cycle 23 spec §8 requires explicit user approval first).

Usage: python scripts/c23_event_parity.py [--charts N]   (N = render charts for the first N charted seed days)
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import c21_fixtures as fixtures_mod
from c21_fixture_parity import XNYS
from c21_reference_check import SEEDS, SPANS
from c21_reference_impl import RefMarket, run_day
from c21_synthetic import generate

from v17.c23_visual.chart_manifest import generate as render_charts
from v17.c23_visual.event_export import data_fingerprint, export
from v17.c23_visual.metrics import candidate_metrics
from v17.c23_visual.parity import compare, engine_stream, reference_stream
from v17.c23_visual.report import DayRow, frame, markdown, row
from v17.smc_sb.config import BASELINE, EXPERIMENT_OTE, StrategyConfig
from v17.smc_sb.data import Market, build_market

OUT = REPO / "out" / "c23"


def run_days(
    label: str,
    mk: Market,
    rm: RefMarket,
    cfg: StrategyConfig,
    days: list,
    rows: list[DayRow],
) -> tuple[list, list]:
    records, ledger, raw = export(mk, cfg, days)
    by_day: dict[str, list] = {}
    for e in ledger:
        by_day.setdefault(e.trading_date, []).append(e)
    for rec, res in zip(records, raw, strict=True):
        evs = by_day.get(rec.trading_date, [])
        trace: list[tuple] = []
        ref_reason, _ = run_day(
            rm, res.day, model=cfg.entry_model, expiry=cfg.order_expiry, trace=trace
        )
        bad = compare(engine_stream(evs, rec.result), reference_stream(trace, ref_reason))
        r = float(res.trade["r"]) if res.trade else math.nan  # type: ignore[arg-type]
        rows.append(row(rec, label, ref_reason, bad, r, candidate_metrics(mk, evs)))
    return records, ledger


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--charts", type=int, default=0)
    args = ap.parse_args()
    rows: list[DayRow] = []
    # hand-built fixtures
    fx = [
        fixtures_mod.Fixture(
            "base", "base", fixtures_mod.m1_frame(fixtures_mod.day_rows(fixtures_mod.BASE))
        ),
        *fixtures_mod.fixtures(),
    ]
    for f in fx:
        cfg = dataclasses.replace(BASELINE, entry_model=f.model, order_expiry=f.expiry)
        mk = build_market("FIX_" + f.name, f.m1, xnys=XNYS, early_close=f.early)
        rm = RefMarket(f.m1, "FIX_" + f.name, xnys=XNYS, early=f.early)
        run_days(f.model, mk, rm, cfg, [fixtures_mod.DAY], rows)
    # six random synthetic seeds, Model A baseline and Model B
    charted_left = args.charts
    for seed in SEEDS:
        start, end = SPANS[seed]
        prim, _ = generate(start, end, seed=seed, partner_seed=seed + 1000)
        name = f"SEED{seed}"
        mk, rm = build_market(name, prim), RefMarket(prim, name)
        days = [d.date() for d in pd.bdate_range(pd.Timestamp(start) + pd.Timedelta(days=31), end)]
        for cfg, label in ((BASELINE, "A"), (EXPERIMENT_OTE, "B")):
            records, ledger = run_days(label, mk, rm, cfg, days, rows)
            if label == "A" and charted_left > 0:
                pick = [r for r in records if r.charted][:charted_left]
                charted_left -= len(pick)
                render_charts(mk, cfg, pick, ledger, OUT / "synthetic_charts", data_fingerprint(mk))
        print(f"seed {seed}: done")
    df = frame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "event_parity_synthetic.csv", index=False)
    (OUT / "event_parity_synthetic.md").write_text(
        markdown(df, "Cycle 23 gate 6 — event parity + metrics (SYNTHETIC ONLY)"), encoding="utf-8"
    )
    n_bad = int((~df.parity_ok).sum())
    print(f"days={len(df)} event mismatches={n_bad} -> {'PASS' if n_bad == 0 else 'FAIL'}")
    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
