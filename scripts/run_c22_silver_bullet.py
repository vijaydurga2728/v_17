"""Cycle 22 — Institutional Silver Bullet Runner (Zero-Lookahead Reform).

Evaluates the reformed Silver Bullet strategy across curated session/symbol slots:
- LDN EURUSD
- LDN GBPUSD
- AM EURUSD
- AM USATECHIDXUSD

Dev period: 2021-01-01 -> 2024-12-31
Holdout:    2025-01-01 -> 2026-12-31
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.data.calendar.archive import load_archive_dir  # noqa: E402
from v17.data.parquet_store import read_bars  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402

OUT = REPO / "out" / "c22"
DEV_START, DEV_END = "2021-01-01", "2024-12-31"
HO_START, HO_END = "2025-01-01", "2026-12-31"


def load_m1_symbol(sym: str) -> pd.DataFrame:
    """Loads combined dev + holdout M1 bars for a symbol."""
    paired = REPO / "data" / "bars_m1_paired" / sym
    if paired.exists():
        return pd.read_parquet(paired)
    root = REPO / ".worktrees" / "sb-6-engine-gate" / "data"
    return pd.concat(
        [read_bars(root=root, symbol=sym, partition=p, dev_only=False) for p in ("dev", "holdout")],
        ignore_index=True,
    )


def load_calendar_blackout_df() -> pd.DataFrame:
    """Loads high-impact calendar events as a DataFrame for blackout checking."""
    cal_dir = REPO / "data" / "calendar"
    if not cal_dir.exists():
        return pd.DataFrame()
    events = load_archive_dir(cal_dir)
    rows = [
        {"currency": e.currency, "timestamp_utc": int(e.at.timestamp() * 1_000_000_000)}
        for e in events
        if e.impact == "high"
    ]
    return pd.DataFrame(rows)


def compute_metrics(trades: pd.DataFrame) -> dict[str, float]:
    """Computes standard performance metrics for a trades DataFrame."""
    if trades.empty:
        return {"n": 0, "pf": float("nan"), "mean_r": float("nan"), "win_rate": float("nan"), "max_dd_r": float("nan")}
    r = trades["r"].to_numpy(np.float64)
    n = len(r)
    wins = r[r > 0]
    losses = r[r < 0]
    tot_win = float(wins.sum()) if len(wins) else 0.0
    tot_loss = float(-losses.sum()) if len(losses) else 0.0
    pf = tot_win / tot_loss if tot_loss > 0 else float("inf")
    mean_r = float(r.mean())
    win_rate = float(len(wins) / n)
    eq = np.r_[0.0, np.cumsum(r)]
    peaks = np.maximum.accumulate(eq)
    dd = float((peaks - eq).max())
    return {
        "n": n,
        "pf": pf,
        "mean_r": mean_r,
        "win_rate": win_rate,
        "max_dd_r": dd,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    calendar_df = load_calendar_blackout_df()
    print(f"Loaded {len(calendar_df)} high-impact calendar blackout events.")
    
    symbols_needed = sorted(list({s for _, s in sb.CURATED_SLOTS}))
    bars_cache: dict[str, sb.Bars] = {}
    
    for sym in symbols_needed:
        print(f"Loading M1 bars for {sym}...")
        df_m1 = load_m1_symbol(sym)
        bars_cache[sym] = sb.prepare(df_m1)
        print(f"  {sym}: {len(bars_cache[sym].ts):,} M1 bars prepared.")
        
    log_lines = []
    print("\n" + "=" * 80)
    print("CYCLE 22: INSTITUTIONAL SILVER BULLET BACKTEST RESULTS")
    print("=" * 80)
    
    for window, sym in sb.CURATED_SLOTS:
        b = bars_cache[sym]
        
        # 1. Dev Period
        t_dev = sb.run_slot_c22(b, sym, window, DEV_START, DEV_END, calendar_df)
        m_dev = compute_metrics(t_dev)
        
        # 2. Holdout Period
        t_ho = sb.run_slot_c22(b, sym, window, HO_START, HO_END, calendar_df)
        m_ho = compute_metrics(t_ho)
        
        # Save individual slot trades
        if not t_dev.empty:
            t_dev.to_csv(OUT / f"trades_dev_{window}_{sym}.csv", index=False)
        if not t_ho.empty:
            t_ho.to_csv(OUT / f"trades_ho_{window}_{sym}.csv", index=False)
            
        # Format log line
        dev_str = (
            f"DEV [2021-2024] n={m_dev['n']:3d} | PF={m_dev['pf']:5.2f} | "
            f"meanR={m_dev['mean_r']:+6.3f} | win={m_dev['win_rate']:4.2f} | DD={m_dev['max_dd_r']:4.1f}R"
        )
        ho_str = (
            f"HO  [2025-2026] n={m_ho['n']:3d} | PF={m_ho['pf']:5.2f} | "
            f"meanR={m_ho['mean_r']:+6.3f} | win={m_ho['win_rate']:4.2f} | DD={m_ho['max_dd_r']:4.1f}R"
        )
        
        header = f"[{window}] {sym:14s}"
        print(f"{header} {dev_str}")
        print(f"{' '*len(header)} {ho_str}")
        log_lines.append(f"{header} {dev_str}")
        log_lines.append(f"{' '*len(header)} {ho_str}")
        
    (REPO / "out" / "c22_run_log.txt").write_text("\n".join(log_lines), encoding="utf-8")
    print("=" * 80)
    print(f"Results written to {REPO / 'out' / 'c22_run_log.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
