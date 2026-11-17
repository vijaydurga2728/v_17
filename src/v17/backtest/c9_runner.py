"""Cycle 9 per-slot runner: data loading (with holdout guard), session prep, metrics.

Holdout discipline (pre-reg §4, §12 Tier 4): ``load_window("holdout")`` refuses
to read unless ``allow_holdout=True`` is passed explicitly. Dev loading reads
only year partitions 2015-2022 from disk, so cycle 9 holdout bars (2023+) are
never read during development.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from v17.setups.c9_pdh_pdl import (
    DEV_END,
    DEV_START,
    HOLDOUT_END,
    HOLDOUT_START,
    SYMBOL,
    Sessions,
    Slot,
    atr_prev,
    build_m15,
    full_rth_days,
    levels,
    sessions_from_m15,
    simulate,
)

DEFAULT_BARS_ROOT = (
    Path(__file__).resolve().parents[3] / ".worktrees" / "sb-6-engine-gate" / "data" / "bars"
)
Window = Literal["dev", "holdout"]


class HoldoutAccessError(RuntimeError):
    pass


def bars_root() -> Path:
    return Path(os.environ.get("V17_BARS_ROOT", str(DEFAULT_BARS_ROOT)))


def _window_bounds(window: Window) -> tuple[str, str]:
    return (DEV_START, DEV_END) if window == "dev" else (HOLDOUT_START, HOLDOUT_END)


def load_m1(window: Window, *, allow_holdout: bool = False, root: Path | None = None,
            months: list[tuple[int, int]] | None = None) -> pd.DataFrame:
    """Read paired M1 bars for the cycle 9 window, by year partition only.

    ``months`` restricts to specific (year, month) pairs (used by smoke tests).
    """
    if window == "holdout" and not allow_holdout:
        raise HoldoutAccessError("cycle 9 holdout is sealed; Tier 4 must pass allow_holdout=True")
    start, end = _window_bounds(window)
    y0, y1 = int(start[:4]), int(end[:4])
    base = (root or bars_root()) / SYMBOL
    frames = []
    for year in range(y0, y1 + 1):
        for part in ("dev", "holdout"):  # cycle 4B partition names; cycle 9 splits by date
            ydir = base / part / f"year={year}"
            if not ydir.exists():
                continue
            for mdir in sorted(ydir.glob("month=*")):
                month = int(mdir.name.split("=")[1])
                if months is not None and (year, month) not in months:
                    continue
                f = mdir / "data.parquet"
                if f.exists():
                    frames.append(pq.read_table(f).to_pandas())
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).sort_values("ts_utc", kind="mergesort")
    lo = pd.Timestamp(start, tz="UTC").value
    hi = (pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).value
    df = df[(df["ts_utc"] >= lo) & (df["ts_utc"] < hi)]
    out, audit = dedupe_m1(df)
    out.attrs["c9_load_audit"] = audit
    return out


class DataIntegrityError(RuntimeError):
    pass


def dedupe_m1(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop exact duplicate rows; raise on conflicting rows that share a ts_utc [IMPL-10].

    Returns (clean_df, audit) with audit = {"rows_in", "exact_duplicates_dropped",
    "conflicting_timestamps"} (the last is always 0 on success).
    """
    rows_in = len(df)
    exact = df.duplicated(keep="first")
    clean = df.loc[~exact]
    clash = clean["ts_utc"].duplicated(keep=False)
    if clash.any():
        n_ts = int(clean.loc[clash, "ts_utc"].nunique())
        first = int(clean.loc[clash, "ts_utc"].iloc[0])
        raise DataIntegrityError(
            f"{n_ts} timestamps have conflicting M1 rows (first ts_utc={first}); "
            "refusing to pick one"
        )
    audit = {"rows_in": rows_in, "exact_duplicates_dropped": int(exact.sum()),
             "conflicting_timestamps": 0}
    return clean.reset_index(drop=True), audit


@dataclass
class Prepared:
    sess: Sessions
    pdh: np.ndarray
    pdl: np.ndarray
    atrp: np.ndarray


def prepare(m1: pd.DataFrame, window: Window) -> Prepared:
    start, end = _window_bounds(window)
    days = full_rth_days(start, end)
    sess = sessions_from_m15(build_m15(m1, days), days)
    pdh, pdl = levels(sess)
    return Prepared(sess, pdh, pdl, atr_prev(sess))


def run_slot(prep: Prepared, slot: Slot, slippage_pts: float = 0.0) -> pd.DataFrame:
    return simulate(prep.sess, prep.pdh, prep.pdl, prep.atrp, slot, slippage_pts)


def metrics(r: np.ndarray) -> dict[str, float]:
    """Tier 1 metrics in R units (pre-reg §12)."""
    r = np.asarray(r, dtype=np.float64)
    n = len(r)
    # [IMPL-11] Sharpe = mean(R)/std(R, ddof=1) per trade. Zero dispersion (all R equal, or a
    # single trade) has no finite ratio: report +inf / 0 / -inf by the sign of mean(R), so the
    # Tier 1 gate "Sharpe >= 0" is exactly "mean(R) >= 0" in every case.
    if n == 0:
        return {"n_trades": 0, "pf": float("nan"), "mean_r": 0.0, "win_rate": float("nan"),
                "max_dd_r": 0.0, "sharpe": float("nan"), "total_r": 0.0}
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses > 0:  # noqa: SIM108 - nested ternary is harder to read
        pf = gains / losses
    else:
        pf = float("inf") if gains > 0 else float("nan")
    eq = np.r_[0.0, np.cumsum(r)]
    max_dd = float((np.maximum.accumulate(eq) - eq).max())
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    mu = float(r.mean())
    if sd > 0:  # noqa: SIM108 - nested ternary is harder to read
        sharpe = mu / sd
    else:
        sharpe = float(np.sign(mu)) * float("inf") if mu != 0 else 0.0
    return {"n_trades": n, "pf": float(pf), "mean_r": float(r.mean()),
            "win_rate": float((r > 0).mean()), "max_dd_r": max_dd, "sharpe": sharpe,
            "total_r": float(r.sum())}


TIER1_PF_MIN = 1.3
TIER1_TRADES_MIN = 100
TIER1_MAX_DD_R = 8.0
TIER1_SHARPE_MIN = 0.0


def tier1_pass(m: dict[str, float]) -> bool:
    """Pre-reg §12 Tier 1. Not loosenable without an ADR."""
    return bool(
        m["n_trades"] >= TIER1_TRADES_MIN
        and m["pf"] >= TIER1_PF_MIN
        and m["max_dd_r"] <= TIER1_MAX_DD_R
        and not np.isnan(m["sharpe"]) and m["sharpe"] >= TIER1_SHARPE_MIN
    )
