"""Analyze exact EURUSD trades from Cycle 22."""

from pathlib import Path
import sys
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df
import v17.setups.c22_silver_bullet as sb

b_eur = sb.prepare(load_m1_symbol("EURUSD"))
cal_df = load_calendar_blackout_df()
sb.SPECS["EURUSD"] = sb.Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006)
t_eur = sb.run_slot_c22(b_eur, "EURUSD", "AM", "2021-01-01", "2026-12-31", cal_df)

n = len(t_eur)
wins = t_eur[t_eur["r"] > 0]
losses = t_eur[t_eur["r"] <= 0]
wr = len(wins) / n * 100.0 if n > 0 else 0.0
gw = wins["r"].sum()
gl = abs(losses["r"].sum())
pf = gw / gl if gl > 0 else 999.0

print(f"Total Trades: {n}")
print(f"Win Rate: {wr:.1f}% ({len(wins)}W / {len(losses)}L)")
print(f"Profit Factor: {pf:.2f}")
print(f"Net R: {t_eur['r'].sum():+.2f} R")
print("\nTrades Breakdown:")
for idx, r in t_eur.iterrows():
    side_str = "BUY" if r["side"] == 1 else "SELL"
    res_str = "WIN " if r["r"] > 0 else "LOSS"
    print(f"{r['day']} | {side_str:4s} | Entry: {r['entry']:.5f} | SL: {r['sl']:.5f} | TP: {r['tp']:.5f} | R: {r['r']:+.2f} | {res_str} ({r['reason']})")
