"""Cycle 8 Donchian channel breakout — dev grid runner.

Pre-reg: docs/superpowers/specs/2026-11-16-cycle8-donchian-prereg.md.

Loads M1 paired from data/bars_m1_paired/{SYMBOL}, resamples to D1 UTC-day,
runs 18 configs per symbol (lookback_entry x lookback_exit x direction).
Writes:
  out/c8/dev_grid_{SYMBOL}.csv
  out/c8/dev_grid.log
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = {
    "LIGHTCMDUSD": {"dev_start": "2015-01-01", "dev_end": "2023-12-31"},
    "DOLLARIDXUSD": {"dev_start": "2018-01-01", "dev_end": "2023-12-31"},
}

LOOKBACK_ENTRY_GRID = (20, 40, 55)
LOOKBACK_EXIT_GRID = (10, 20)
DIRECTION_GRID = ("long_only", "short_only", "both")

SRC_ROOT = Path("data/bars_m1_paired")
OUT_DIR = Path("out/c8")
ATR_WINDOW = 20


def _load_d1(symbol: str) -> pd.DataFrame:
    part_root = SRC_ROOT / symbol
    files = sorted(part_root.glob("year=*/*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.sort_values("ts_utc").reset_index(drop=True)
    ts = pd.to_datetime(df["ts_utc"], unit="ns", utc=True)
    df["utc_date"] = ts.dt.strftime("%Y-%m-%d")
    g = df.groupby("utc_date", sort=True, as_index=False)
    d1 = g.agg(
        ts_utc=("ts_utc", "first"),
        bid_o=("bid_o", "first"),
        bid_h=("bid_h", "max"),
        bid_l=("bid_l", "min"),
        bid_c=("bid_c", "last"),
        ask_o=("ask_o", "first"),
        ask_h=("ask_h", "max"),
        ask_l=("ask_l", "min"),
        ask_c=("ask_c", "last"),
        n_m1_bars=("ts_utc", "count"),
    )
    d1 = d1[d1["n_m1_bars"] >= 60].copy()
    d1["mid_c"] = (d1["bid_c"] + d1["ask_c"]) / 2.0
    d1["mid_h"] = (d1["bid_h"] + d1["ask_h"]) / 2.0
    d1["mid_l"] = (d1["bid_l"] + d1["ask_l"]) / 2.0
    tr = pd.concat([
        (d1["mid_h"] - d1["mid_l"]).abs(),
        (d1["mid_h"] - d1["mid_c"].shift(1)).abs(),
        (d1["mid_l"] - d1["mid_c"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    d1["atr20_prev"] = tr.rolling(ATR_WINDOW).mean().shift(1)
    return d1.reset_index(drop=True)


def _simulate(d1: pd.DataFrame, lb_e: int, lb_x: int, direction: str) -> pd.DataFrame:
    hi_e = d1["mid_h"].shift(1).rolling(lb_e).max()
    lo_e = d1["mid_l"].shift(1).rolling(lb_e).min()
    hi_x = d1["mid_h"].shift(1).rolling(lb_x).max()
    lo_x = d1["mid_l"].shift(1).rolling(lb_x).min()
    c = d1["mid_c"]

    pos = 0
    entry_px = 0.0
    entry_atr = 0.0
    trades = []
    n = len(d1)
    for i in range(1, n - 1):  # need i+1 for fill
        atr_prev = d1["atr20_prev"].iat[i]
        if not math.isfinite(atr_prev) or atr_prev <= 0:
            continue
        long_entry = c.iat[i] > hi_e.iat[i]
        short_entry = c.iat[i] < lo_e.iat[i]
        long_exit_channel = pos > 0 and c.iat[i] < lo_x.iat[i]
        short_exit_channel = pos < 0 and c.iat[i] > hi_x.iat[i]
        # Flip signal: only applies under direction="both".
        long_to_short_flip = direction == "both" and pos > 0 and short_entry
        short_to_long_flip = direction == "both" and pos < 0 and long_entry

        if pos > 0 and (long_exit_channel or long_to_short_flip):
            exit_px = d1["bid_o"].iat[i + 1]
            pnl_pts = exit_px - entry_px
            r = pnl_pts / entry_atr
            trades.append(("long", entry_px, exit_px, entry_atr, pnl_pts, r))
            pos = 0
        elif pos < 0 and (short_exit_channel or short_to_long_flip):
            exit_px = d1["ask_o"].iat[i + 1]
            pnl_pts = entry_px - exit_px
            r = pnl_pts / entry_atr
            trades.append(("short", entry_px, exit_px, entry_atr, pnl_pts, r))
            pos = 0

        if pos == 0:
            if direction in ("long_only", "both") and long_entry:
                entry_px = d1["ask_o"].iat[i + 1]
                entry_atr = atr_prev
                pos = +1
            elif direction in ("short_only", "both") and short_entry:
                entry_px = d1["bid_o"].iat[i + 1]
                entry_atr = atr_prev
                pos = -1

    # Flat at end: close at last mid.
    if pos != 0:
        last_i = n - 1
        if pos > 0:
            exit_px = d1["bid_c"].iat[last_i]
            pnl_pts = exit_px - entry_px
            trades.append(("long", entry_px, exit_px, entry_atr, pnl_pts, pnl_pts / entry_atr))
        else:
            exit_px = d1["ask_c"].iat[last_i]
            pnl_pts = entry_px - exit_px
            trades.append(("short", entry_px, exit_px, entry_atr, pnl_pts, pnl_pts / entry_atr))

    if not trades:
        return pd.DataFrame()
    return pd.DataFrame(trades, columns=["side", "entry", "exit", "entry_atr", "pnl_pts", "r"])


def _metrics(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "pf": 0.0, "mean_r": 0.0, "sharpe": 0.0, "wr": 0.0, "max_dd_r": 0.0, "sum_r": 0.0}
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
    max_dd = (peak - eq).max()
    return {
        "trades": int(n), "pf": float(pf), "mean_r": float(mean_r),
        "sharpe": float(sharpe), "wr": float(wr),
        "max_dd_r": float(max_dd), "sum_r": float(eq[-1]),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / "dev_grid.log"
    log_path.write_text("", encoding="utf-8")

    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    for symbol, win in SYMBOLS.items():
        log(f"=== {symbol} ===")
        t0 = time.time()
        d1 = _load_d1(symbol)
        d1 = d1[(d1["utc_date"] >= win["dev_start"]) & (d1["utc_date"] <= win["dev_end"])].reset_index(drop=True)
        log(f"[{symbol}] loaded {len(d1)} D1 UTC-days ({win['dev_start']}..{win['dev_end']}) in {time.time()-t0:.1f}s")

        results = []
        total = len(LOOKBACK_ENTRY_GRID) * len(LOOKBACK_EXIT_GRID) * len(DIRECTION_GRID)
        i = 0
        for lb_e in LOOKBACK_ENTRY_GRID:
            for lb_x in LOOKBACK_EXIT_GRID:
                for dr in DIRECTION_GRID:
                    i += 1
                    ts0 = time.time()
                    tr = _simulate(d1, lb_e, lb_x, dr)
                    m = _metrics(tr)
                    m.update({"symbol": symbol, "lookback_entry": lb_e, "lookback_exit": lb_x, "direction": dr})
                    results.append(m)
                    log(f"[{symbol}] [{i}/{total}] le={lb_e:3d} lx={lb_x:3d} dr={dr:10s} trades={m['trades']:4d} pf={m['pf']:.3f} mean_r={m['mean_r']:+.4f} sharpe={m['sharpe']:+.3f} max_dd={m['max_dd_r']:.2f}R took={time.time()-ts0:.2f}s")

        cols = ["symbol", "lookback_entry", "lookback_exit", "direction", "trades",
                "pf", "mean_r", "sharpe", "wr", "max_dd_r", "sum_r"]
        out = pd.DataFrame(results)[cols]
        csv_path = OUT_DIR / f"dev_grid_{symbol}.csv"
        out.to_csv(csv_path, index=False)
        log(f"[{symbol}] wrote {csv_path}")

    log("END grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
