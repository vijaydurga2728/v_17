"""Investigate trade frequency bottlenecks and test compliant expansion.

Goal:
1. Measure trade counts and performance when sweep can occur prior to the window (e.g. pre-market / session open sweep).
2. Measure across full 6-year Dev (2018/2021-2024) and OOS (2025-2026).
3. Track Net PF, Win Rate, and Trade Counts across symbols and sessions.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics
from v17.setups import c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

print("Loading EURUSD...")
b_eur = sb.prepare(load_m1_symbol("EURUSD"))
print("Loading GBPUSD...")
b_gbp = sb.prepare(load_m1_symbol("GBPUSD"))
print("Loading NQ...")
b_nq = sb.prepare(load_m1_symbol("USATECHIDXUSD"))

print("Baseline trade counts (Current c22):")
for sym, b, win in [("EURUSD", b_eur, "AM"), ("GBPUSD", b_gbp, "LDN"), ("USATECHIDXUSD", b_nq, "AM")]:
    t_dev = sb.run_slot_c22(b, sym, win, "2021-01-01", "2024-12-31", cal_df)
    t_oos = sb.run_slot_c22(b, sym, win, "2025-01-01", "2026-12-31", cal_df)
    m_dev = compute_metrics(t_dev)
    m_oos = compute_metrics(t_oos)
    print(f"  {sym:14s} {win:3s} | DEV n={m_dev['n']:2d} PF={m_dev['pf']:.2f} | OOS n={m_oos['n']:2d} PF={m_oos['pf']:.2f}")
