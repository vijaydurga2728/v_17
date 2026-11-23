"""Comprehensive 6-Year Verification of Cycle 24 Silver Bullet Antigravity."""

from pathlib import Path
import sys
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402
from v17.setups.c24_silver_bullet_antigravity import run_slot_c24, SPECS  # noqa: E402


def run_test(sym: str, window: str, label: str) -> pd.DataFrame:
    print(f"\n=======================================================")
    print(f"VERIFYING CYCLE 24 ANTIGRAVITY: {sym} [{window}] — {label}")
    print(f"Period: 2021-01-01 to 2026-12-31 (6-Year Continuous)")
    print(f"=======================================================")

    raw_df = load_m1_symbol(sym)
    b = sb.prepare(raw_df)
    cal_df = load_calendar_blackout_df()

    trades_df = run_slot_c24(b, sym, window, "2021-01-01", "2026-12-31", cal_df)
    if len(trades_df) == 0:
        print(f"[{sym}] 0 trades found.")
        return trades_df

    n = len(trades_df)
    wins = trades_df[trades_df["r"] > 0]
    losses = trades_df[trades_df["r"] <= 0]
    wr = len(wins) / n * 100.0

    gross_win = wins["r"].sum()
    gross_loss = abs(losses["r"].sum())
    pf = gross_win / gross_loss if gross_loss > 0 else 999.0
    net_r = trades_df["r"].sum()
    avg_r = trades_df["r"].mean()

    # Drawdown
    cum_r = trades_df["r"].cumsum()
    peak = cum_r.cummax()
    max_dd = (peak - cum_r).max()

    # Split Dev (2021-2024) vs OOS Holdout (2025-2026)
    dev_trades = trades_df[trades_df["day"] <= "2024-12-31"]
    ho_trades = trades_df[trades_df["day"] > "2024-12-31"]

    dev_pf = (dev_trades[dev_trades["r"] > 0]["r"].sum() / abs(dev_trades[dev_trades["r"] <= 0]["r"].sum())) if len(dev_trades[dev_trades["r"] <= 0]) > 0 else 999.0
    ho_pf = (ho_trades[ho_trades["r"] > 0]["r"].sum() / abs(ho_trades[ho_trades["r"] <= 0]["r"].sum())) if len(ho_trades[ho_trades["r"] <= 0]) > 0 else 999.0

    print(f"[{sym}] 6-YEAR COMBINED RESULTS:")
    print(f"  Total Trades:     {n}")
    print(f"  Win Rate:         {wr:.1f}% ({len(wins)}W / {len(losses)}L)")
    print(f"  Profit Factor:    {pf:.2f} (Dev PF: {dev_pf:.2f} | Holdout OOS PF: {ho_pf:.2f})")
    print(f"  Net R:            {net_r:+.2f} R")
    print(f"  Mean R/trade:     {avg_r:+.3f} R")
    print(f"  Max Drawdown:     {max_dd:.2f} R")

    return trades_df


if __name__ == "__main__":
    t_eur = run_test("EURUSD", "AM", "NY AM Opening Drive")
    t_gbp = run_test("GBPUSD", "LDN", "London Silver Bullet")

    all_t = pd.concat([t_eur, t_gbp], ignore_index=True).sort_values("fill_i").reset_index(drop=True)
    n_all = len(all_t)
    w_all = all_t[all_t["r"] > 0]
    l_all = all_t[all_t["r"] <= 0]
    wr_all = len(w_all) / n_all * 100.0
    pf_all = w_all["r"].sum() / abs(l_all["r"].sum())

    print("\n" + "=" * 80)
    print(f"CYCLE 24 PORTFOLIO COMBINED: {n_all} Trades | {wr_all:.1f}% WR | {pf_all:.2f} Profit Factor | Net {all_t['r'].sum():+.2f} R")
    print("=" * 80)
