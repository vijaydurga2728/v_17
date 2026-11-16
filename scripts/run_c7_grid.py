"""Cycle 7 gap-continuation SPX D1 grid runner.

Pre-reg: docs/superpowers/specs/2026-11-16-cycle7-gap-continuation-prereg.md.

Loads data/bars_d1_rth/USA500IDXUSD/, runs 36 configs = 4 gap_min x 3 stop_R x 3 direction.
Writes:
  out/c7/dev_grid.csv  - one row per config.
  out/c7/dev_grid.log  - progress log.

No MCPT here; MCPT is a separate step after Tier 1 pass.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


SYMBOL = "USA500IDXUSD"
BARS_ROOT = Path("data/bars_d1_rth") / SYMBOL
OUT_DIR = Path("out/c7")
DEV_START = "2015-01-01"
DEV_END = "2023-12-31"

GAP_MIN_GRID = (0.0015, 0.0025, 0.0040, 0.0060)
STOP_R_GRID = (0.5, 1.0, 1.5)
DIRECTION_GRID = ("long_only", "short_only", "both")
ATR_WINDOW = 14


def _load_dev() -> pd.DataFrame:
    files = sorted(BARS_ROOT.glob("year=*/data.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.sort_values("ny_date").reset_index(drop=True)
    df = df[(df["ny_date"] >= DEV_START) & (df["ny_date"] <= DEV_END)].reset_index(drop=True)
    # Prior-day fields (causal).
    df["prev_mid_c"] = df["mid_c"].shift(1)
    tr = pd.concat([
        (df["mid_h"] - df["mid_l"]).abs(),
        (df["mid_h"] - df["prev_mid_c"]).abs(),
        (df["mid_l"] - df["prev_mid_c"]).abs(),
    ], axis=1).max(axis=1)
    df["atr14_prev"] = tr.rolling(ATR_WINDOW).mean().shift(1)
    df["gap"] = df["mid_o"] / df["prev_mid_c"] - 1
    df = df.dropna(subset=["prev_mid_c", "atr14_prev", "gap"]).reset_index(drop=True)
    return df


def _simulate(df: pd.DataFrame, gap_min: float, stop_r: float, direction: str) -> pd.DataFrame:
    rows = []
    for row in df.itertuples(index=False):
        gap = row.gap
        atr = row.atr14_prev
        if not math.isfinite(gap) or not math.isfinite(atr) or atr <= 0:
            continue
        side = None
        if direction in ("long_only", "both") and gap > gap_min:
            side = "long"
        elif direction in ("short_only", "both") and gap < -gap_min:
            side = "short"
        if side is None:
            continue
        stop_dist = stop_r * atr
        if side == "long":
            entry = row.ask_o
            stop = entry - stop_dist
            if row.bid_l <= stop:
                exit_px = stop
                reason = "stop"
            else:
                exit_px = row.bid_c
                reason = "eod"
            pnl_pts = exit_px - entry
        else:
            entry = row.bid_o
            stop = entry + stop_dist
            if row.ask_h >= stop:
                exit_px = stop
                reason = "stop"
            else:
                exit_px = row.ask_c
                reason = "eod"
            pnl_pts = entry - exit_px
        r = pnl_pts / stop_dist
        rows.append((row.ny_date, side, entry, exit_px, stop_dist, pnl_pts, r, reason))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["ny_date", "side", "entry", "exit", "stop_dist", "pnl_pts", "r", "reason"])


def _metrics(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {
            "trades": 0, "pf": 0.0, "mean_r": 0.0, "sharpe": 0.0,
            "wr": 0.0, "max_dd_r": 0.0, "sum_r": 0.0,
        }
    r = trades["r"].to_numpy(dtype=float)
    gp = r[r > 0].sum()
    gl = -r[r < 0].sum()
    pf = gp / gl if gl > 0 else float("inf")
    mean_r = r.mean()
    sd = r.std(ddof=1) if n > 1 else 0.0
    sharpe = (mean_r / sd) * math.sqrt(252) if sd > 0 else 0.0
    wr = (r > 0).mean()
    eq = np.cumsum(r)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    max_dd = dd.max()
    return {
        "trades": int(n),
        "pf": float(pf),
        "mean_r": float(mean_r),
        "sharpe": float(sharpe),
        "wr": float(wr),
        "max_dd_r": float(max_dd),
        "sum_r": float(eq[-1]),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / "dev_grid.log"
    csv_path = OUT_DIR / "dev_grid.csv"

    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    log_path.write_text("", encoding="utf-8")
    log(f"START grid dev {DEV_START}..{DEV_END}")
    df = _load_dev()
    log(f"loaded {len(df)} RTH days post-ATR warmup")

    results = []
    total = len(GAP_MIN_GRID) * len(STOP_R_GRID) * len(DIRECTION_GRID)
    i = 0
    for gm in GAP_MIN_GRID:
        for sr in STOP_R_GRID:
            for dr in DIRECTION_GRID:
                i += 1
                t0 = time.time()
                trades = _simulate(df, gm, sr, dr)
                m = _metrics(trades)
                m.update({"gap_min": gm, "stop_R": sr, "direction": dr})
                results.append(m)
                log(f"[{i}/{total}] gm={gm} sr={sr} dr={dr:10s} trades={m['trades']:4d} pf={m['pf']:.3f} mean_r={m['mean_r']:+.4f} sharpe={m['sharpe']:+.3f} max_dd={m['max_dd_r']:.2f}R took={time.time()-t0:.2f}s")

    cols = ["gap_min", "stop_R", "direction", "trades", "pf", "mean_r", "sharpe", "wr", "max_dd_r", "sum_r"]
    out = pd.DataFrame(results)[cols]
    out.to_csv(csv_path, index=False)
    log(f"wrote {csv_path} ({len(out)} rows)")
    log("END grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
