import sys
from pathlib import Path
import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df
import v17.setups.c24_silver_bullet_antigravity as c24
import v17.setups.c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

print("Testing C24 Silver Bullet Antigravity across symbols...")
for sym, win in [("EURUSD", "AM"), ("GBPUSD", "LDN"), ("USATECHIDXUSD", "AM"), ("USA500IDXUSD", "AM")]:
    b = sb.prepare(load_m1_symbol(sym))
    t = c24.run_slot_c24(b, sym, win, "2021-01-01", "2026-12-31", cal_df)
    if len(t) > 0:
        w = t[t["r"] > 0]
        l = t[t["r"] <= 0]
        wr = len(w) / len(t) * 100.0
        gw = w["r"].sum()
        gl = abs(l["r"].sum())
        pf = gw / gl if gl > 0 else 999.0
        print(f"{sym:14s} {win:4s} | Trades: {len(t):2d} | WR: {wr:5.1f}% ({len(w):2d}W / {len(l):2d}L) | PF: {pf:4.2f} | Net: {t['r'].sum():+6.2f} R")
    else:
        print(f"{sym:14s} {win:4s} | Trades: 0")
