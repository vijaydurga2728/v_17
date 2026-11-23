import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics
from v17.setups import c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()
print("=" * 80)
print("EVALUATING C22 SILVER BULLET OOS (2025-2026)")
print("=" * 80)

slots = [
    ("EURUSD", "LDN"),
    ("EURUSD", "AM"),
    ("GBPUSD", "LDN"),
    ("USATECHIDXUSD", "AM"),
]

all_oos = []
for sym, win in slots:
    raw = load_m1_symbol(sym)
    b = sb.prepare(raw)
    t_oos = sb.run_slot_c22(b, sym, win, "2025-01-01", "2026-12-31", cal_df)
    m = compute_metrics(t_oos)
    print(f"{sym:14s} {win:3s} | OOS n={m['n']:2d} | WR={m['win_rate']*100:4.1f}% | PF={m['pf']:4.2f} | MeanR={m['mean_r']:+.3f} | MaxDD={m['max_dd_r']:4.1f}R")
    if not t_oos.empty:
        t_oos["slot"] = f"{sym}_{win}"
        all_oos.append(t_oos)

if all_oos:
    port = pd.concat(all_oos, ignore_index=True)
    m_port = compute_metrics(port)
    print("=" * 80)
    print(f"PORTFOLIO TOTAL OOS: n={m_port['n']} | WR={m_port['win_rate']*100:.1f}% | PF={m_port['pf']:.2f} | MeanR={m_port['mean_r']:+.3f} | MaxDD={m_port['max_dd_r']:.2f}R")
