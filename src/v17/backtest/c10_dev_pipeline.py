"""Cycle 10 dev-only validation (Tier 1, Tier 2, Tier 3). Holdout is never requested.

Outputs in ``out_dir``: data_audit.json, grid_report.csv, slippage_sensitivity.csv,
trades/<slot>.parquet, mcpt_report.csv, mcpt_perms_<slot>.parquet, run_manifest.json.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v17.backtest.c9_runner import load_m1, metrics, tier1_pass
from v17.setups.c9_pdh_pdl import DEV_END, DEV_START, full_rth_days
from v17.setups.c10_intraday_momentum import (
    I_1000,
    I_1530_ENTRY,
    I_1530_SIG,
    I_LAST,
    SLOTS,
    DayGrid,
    build_grid,
    prev_close,
    r_unit_frac,
    run_slot,
    z_tradeable_days,
)
from v17.validation.c10_mcpt import N_PERMS, run_mcpt, slot_seed

TIER2_ALPHA = 0.05
TIER3_ALPHA = 0.05 / 135  # 0.000370370; pre-reg §10
log = logging.getLogger("c10.phase4")


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    return res.stdout.strip()


def data_audit(m1: pd.DataFrame, g: DayGrid) -> dict[str, Any]:
    load = dict(m1.attrs.get("c9_load_audit", {}))
    full = full_rth_days(DEV_START, DEV_END)
    bars = np.isfinite(g["mid_c"])
    return {
        "window": [DEV_START, DEV_END], "load": load,
        "holdout_files_read": [f for f in load.get("files_read", [])
                               if int(f.split("year=")[1][:4]) >= 2023],
        "xnys_full_days": len(full), "days_with_data": g.n_days,
        "full_days_without_data": sorted(set(full.astype(str)) - set(g.dates.astype(str))),
        "missing_rth_minutes_total": int((~bars).sum()),
        "days_with_any_missing_minute": int((~bars).any(axis=1).sum()),
        "days_missing_10_00_signal_bar": int((~bars[:, I_1000]).sum()),
        "days_missing_15_30_signal_bar": int((~bars[:, I_1530_SIG]).sum()),
        "days_missing_entry_bar": int((~np.isfinite(g["ask_o"][:, I_1530_ENTRY])).sum()),
        "days_missing_16_00_bar": int((~bars[:, I_LAST]).sum()),
        "days_without_prev_close": int(np.isnan(prev_close(g)).sum()),
        "days_without_r_unit": int(np.isnan(r_unit_frac(g)).sum()),
        "days_z_not_tradeable": int((~z_tradeable_days(g)).sum()),
        "zero_volume_rth_minutes": int(((g["vol"] == 0) & bars).sum()),
    }


def run_dev(out_dir: Path, *, bars_root: Path | None = None, n_perms: int = N_PERMS,
            repo: Path | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trades").mkdir(exist_ok=True)
    repo = repo or Path(__file__).resolve().parents[3]
    t0 = time.time()
    man: dict[str, Any] = {
        "phase": "cycle10-phase4-dev", "window": [DEV_START, DEV_END],
        "git_head": _git(repo, "rev-parse", "HEAD"),
        "git_dirty_paths": _git(repo, "status", "--porcelain", "--", "src", "scripts", "tests"),
        "n_perms": n_perms, "official_gate_run": n_perms == N_PERMS,
        "tier2_alpha": TIER2_ALPHA, "tier3_alpha": TIER3_ALPHA,
        "started_utc": pd.Timestamp.now(tz="UTC").isoformat(), "errors": [],
    }
    log.info("c10 dev run: n_perms=%d official=%s head=%s", n_perms, man["official_gate_run"],
             man["git_head"])
    m1 = load_m1("dev", root=bars_root)
    g = build_grid(m1, DEV_START, DEV_END)
    audit = data_audit(m1, g)
    (out_dir / "data_audit.json").write_text(json.dumps(audit, indent=2, default=str), "utf-8")
    if audit["holdout_files_read"]:
        raise RuntimeError(f"holdout files were read: {audit['holdout_files_read']}")

    rows, sens, trades = [], [], {}
    for idx, slot in enumerate(SLOTS):
        tr0 = run_slot(g, slot, 0.0)
        tr1 = run_slot(g, slot, 1.0)
        trades[slot] = tr0
        tr0.to_frame(g).to_parquet(out_dir / "trades" / f"{slot}.parquet", index=False)
        m0, m1_ = metrics(tr0.r), metrics(tr1.r)
        rows.append({"slot_index": idx, "slot": slot, **m0, "tier1_pass": tier1_pass(m0),
                     "n_long": int((tr0.side == 1).sum())})
        sens.append({"slot": slot, **{f"{k}_0pt": v for k, v in m0.items()},
                     **{f"{k}_1pt": v for k, v in m1_.items()}, "tier1_pass_1pt": tier1_pass(m1_)})
    grid = pd.DataFrame(rows)
    grid.to_csv(out_dir / "grid_report.csv", index=False)
    pd.DataFrame(sens).to_csv(out_dir / "slippage_sensitivity.csv", index=False)
    log.info("Tier 1 pass: %s", list(grid.loc[grid["tier1_pass"], "slot"]))

    report = []
    for slot in SLOTS:
        t1 = bool(grid.loc[grid["slot"] == slot, "tier1_pass"].iloc[0])
        row: dict[str, Any] = {"slot": slot, "tier1_pass": t1, "seed": slot_seed(slot),
                               "tier2_pass": False, "tier3_pass": False}
        if not t1:
            row["status"] = "not_run: tier1_fail"
        else:
            ts = time.perf_counter()
            try:
                res, perms = run_mcpt(trades[slot], slot, n_perms=n_perms)
                perms.to_parquet(out_dir / f"mcpt_perms_{slot}.parquet", index=False)
                row.update(status="ok", p_value=res.p_value, n_perms=res.n_perms,
                           exceedances=res.exceedances, observed_mean_r=res.observed_mean_r,
                           tier2_pass=res.p_value <= TIER2_ALPHA,
                           tier3_pass=res.p_value <= TIER3_ALPHA)
                log.info("MCPT %s p=%.6g exceed=%d", slot, res.p_value, res.exceedances)
            except Exception as exc:  # record, never skip silently
                row["status"] = f"error: {type(exc).__name__}: {exc}"
                man["errors"].append(f"{slot}: {row['status']}")
                log.error("MCPT FAILED %s\n%s", slot, traceback.format_exc())
            row["runtime_s"] = round(time.perf_counter() - ts, 1)
        report.append(row)
    rep = pd.DataFrame(report)
    rep.to_csv(out_dir / "mcpt_report.csv", index=False)
    man.update(
        finished_utc=pd.Timestamp.now(tz="UTC").isoformat(), runtime_s=round(time.time() - t0, 1),
        tier1_pass=list(rep.loc[rep["tier1_pass"], "slot"]),
        tier2_pass=list(rep.loc[rep["tier2_pass"], "slot"]),
        tier3_pass=list(rep.loc[rep["tier3_pass"], "slot"]),
        verdict=("DEV GATES PASSED (holdout sealed; Tier 4 needs separate authorization)"
                 if man["official_gate_run"] and rep["tier3_pass"].any()
                 else "NO SLOT PASSED DEV GATES" if man["official_gate_run"]
                 else "TEST RUN - not a gate verdict (n_perms != 100000)"),
    )
    (out_dir / "run_manifest.json").write_text(json.dumps(man, indent=2, default=str), "utf-8")
    log.info("verdict: %s", man["verdict"])
    return man
