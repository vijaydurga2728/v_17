"""Cycle 9 Phase 4 — development-only validation pipeline (Tier 1, Tier 2, Tier 3).

Authorized 2026-11-17 for the dev window 2015-01-01..2022-12-31 only. This module
never requests holdout data: it calls ``load_m1("dev")`` and nothing else, and it
refuses to write a gate verdict unless the MCPT used the pre-registered 100,000
permutations.

Outputs (in ``out_dir``):
  data_audit.json              load/duplicate audit, files read, calendar + session coverage
  grid_report.csv              12 slots, baseline (0 pt), Tier 1 metrics + pass flag
  slippage_sensitivity.csv     Tier 1 metrics at 0 pt vs +1 pt side by side (reporting)
  trades/<slot_id>.parquet     baseline trade lists
  mcpt_report.csv              all 12 slots: Tier 1/2/3 status, p, exceedances, seed, errors
  mcpt_perms_<slot_id>.parquet per-permutation log for every slot that ran MCPT
  run_manifest.json            git commit, dirty flag, args, timings, thresholds, verdict
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from v17.backtest.c9_grid import run_grid
from v17.backtest.c9_runner import Prepared, load_m1, prepare
from v17.setups.c9_pdh_pdl import (
    DEV_END,
    DEV_START,
    N_TRADABLE_BINS,
    Slot,
    all_slots,
    entry_eligible,
    full_rth_days,
)
from v17.validation.c9_mcpt import N_PERMS, run_mcpt, slot_seed

TIER2_ALPHA = 0.05
TIER3_ALPHA = 0.05 / 132  # 0.0003787879; ADR 001 H, permanent
log = logging.getLogger("c9.phase4")


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    return res.stdout.strip()


def data_audit(m1: pd.DataFrame, prep: Prepared) -> dict[str, Any]:
    load = dict(m1.attrs.get("c9_load_audit", {}))
    sess = prep.sess
    full_days = full_rth_days(DEV_START, DEV_END)
    present = set(sess.dates.astype(str))
    lens = np.diff(sess.offsets)
    return {
        "window": {"start": DEV_START, "end": DEV_END},
        "load": load,
        "holdout_files_read": [f for f in load.get("files_read", [])
                               if int(f.split("year=")[1][:4]) >= 2023],
        "m1_ts_min_utc": int(m1["ts_utc"].min()) if len(m1) else None,
        "m1_ts_max_utc": int(m1["ts_utc"].max()) if len(m1) else None,
        "xnys_full_days": len(full_days),
        "sessions_with_data": sess.n_sessions,
        "full_days_without_data": sorted(set(full_days.astype(str)) - present),
        "sessions_lt_25_bins": int((lens < N_TRADABLE_BINS).sum()),
        "sessions_not_entry_eligible": int((~entry_eligible(sess)).sum()),
        "sessions_without_levels": int(np.isnan(prep.pdh).sum()),
        "m15_bars": len(sess.bins),
    }


def run_mcpt_stage(prep: Prepared, slots: list[Slot], out_dir: Path,
                   n_perms: int = N_PERMS) -> list[dict[str, Any]]:
    """Tier 2 MCPT for each slot in ``slots``; one row per slot, errors recorded, never skipped."""
    rows = []
    for slot in slots:
        t0 = time.perf_counter()
        row: dict[str, Any] = {"slot_id": slot.slot_id, "seed": slot_seed(slot), "n_perms": n_perms}
        try:
            log.info("MCPT start %s (%d perms, seed %d)", slot.slot_id, n_perms, row["seed"])
            res, observed, perms = run_mcpt(prep.sess, slot, n_perms=n_perms)
            perms.to_parquet(out_dir / f"mcpt_perms_{slot.slot_id}.parquet", index=False)
            row.update(asdict(res), observed_mean_r=observed, status="ok",
                       tier2_pass=res.p_value <= TIER2_ALPHA, tier3_pass=res.p_value <= TIER3_ALPHA)
            log.info("MCPT done  %s p=%.6g exceedances=%d", slot.slot_id, res.p_value,
                     res.exceedances)
        except Exception as exc:
            row.update(status=f"error: {type(exc).__name__}: {exc}", tier2_pass=False,
                       tier3_pass=False)
            log.error("MCPT FAILED %s\n%s", slot.slot_id, traceback.format_exc())
        row["runtime_s"] = round(time.perf_counter() - t0, 1)
        rows.append(row)
    return rows


def run_dev(out_dir: Path, *, bars_root: Path | None = None, n_perms: int = N_PERMS,
            repo: Path | None = None) -> dict[str, Any]:
    """Full Phase 4 dev run. Returns the manifest (also written to run_manifest.json)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trades").mkdir(exist_ok=True)
    repo = repo or Path(__file__).resolve().parents[3]
    t_start = time.time()
    manifest: dict[str, Any] = {
        "phase": "cycle9-phase4-dev", "window": [DEV_START, DEV_END],
        "git_head": _git(repo, "rev-parse", "HEAD"),
        "git_dirty_paths": _git(repo, "status", "--porcelain", "--", "src", "scripts", "tests"),
        "n_perms": n_perms, "official_gate_run": n_perms == N_PERMS,
        "tier2_alpha": TIER2_ALPHA, "tier3_alpha": TIER3_ALPHA,
        "started_utc": pd.Timestamp.now(tz="UTC").isoformat(), "errors": [],
    }
    log.info("Phase 4 dev run: n_perms=%d official=%s head=%s", n_perms,
             manifest["official_gate_run"], manifest["git_head"])

    m1 = load_m1("dev", root=bars_root)
    prep = prepare(m1, "dev")
    audit = data_audit(m1, prep)
    (out_dir / "data_audit.json").write_text(json.dumps(audit, indent=2, default=str), "utf-8")
    if audit["holdout_files_read"]:
        raise RuntimeError(f"holdout files were read: {audit['holdout_files_read']}")
    log.info("data audit: %d sessions, %d exact dupes dropped, %d missing days",
             audit["sessions_with_data"], audit["load"].get("exact_duplicates_dropped", -1),
             len(audit["full_days_without_data"]))

    base, trades = run_grid(prep, 0.0)
    slip, _ = run_grid(prep, 1.0)
    base.to_csv(out_dir / "grid_report.csv", index=False)
    for slot_id, tl in trades.items():
        tl.to_parquet(out_dir / "trades" / f"{slot_id}.parquet", index=False)
    cols = ["n_trades", "pf", "mean_r", "win_rate", "max_dd_r", "sharpe", "total_r", "tier1_pass"]
    sens = base[["slot_index", "slot_id", *cols]].merge(
        slip[["slot_id", *cols]], on="slot_id", suffixes=("_0pt", "_1pt"))
    sens.to_csv(out_dir / "slippage_sensitivity.csv", index=False)
    log.info("Tier 1 pass: %d / 12", int(base["tier1_pass"].sum()))

    slots = all_slots()
    t1 = dict(zip(base["slot_id"], base["tier1_pass"].astype(bool), strict=True))
    passed = [s for s in slots if t1[s.slot_id]]
    mrows = {r["slot_id"]: r for r in run_mcpt_stage(prep, passed, out_dir, n_perms)}
    report = []
    for s in slots:
        t1 = bool(base.loc[base["slot_id"] == s.slot_id, "tier1_pass"].iloc[0])
        r = mrows.get(s.slot_id, {"slot_id": s.slot_id, "seed": slot_seed(s),
                                  "status": "not_run: tier1_fail", "tier2_pass": False,
                                  "tier3_pass": False})
        report.append({"slot_id": s.slot_id, "tier1_pass": t1, **{k: v for k, v in r.items()
                                                                   if k != "slot_id"}})
        if str(r.get("status", "")).startswith("error"):
            manifest["errors"].append(f"{s.slot_id}: {r['status']}")
    rep = pd.DataFrame(report)
    rep.to_csv(out_dir / "mcpt_report.csv", index=False)

    manifest.update(
        finished_utc=pd.Timestamp.now(tz="UTC").isoformat(),
        runtime_s=round(time.time() - t_start, 1),
        tier1_pass=list(rep.loc[rep["tier1_pass"], "slot_id"]),
        tier2_pass=list(rep.loc[rep["tier2_pass"], "slot_id"]),
        tier3_pass=list(rep.loc[rep["tier3_pass"], "slot_id"]),
        verdict=("DEV GATES PASSED (holdout still sealed; Tier 4 needs separate authorization)"
                 if manifest["official_gate_run"] and rep["tier3_pass"].any()
                 else "NO SLOT PASSED DEV GATES" if manifest["official_gate_run"]
                 else "TEST RUN - not a gate verdict (n_perms != 100000)"),
    )
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), "utf-8")
    log.info("verdict: %s", manifest["verdict"])
    return manifest
