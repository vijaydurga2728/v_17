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

# Update specs for index volatility
sb.SPECS["USATECHIDXUSD"] = sb.Spec(min_stop=8.0, max_stop=120.0, slip=0.5, commission_rt=0.0)
sb.SPECS["USA500IDXUSD"] = sb.Spec(min_stop=1.5, max_stop=25.0, slip=0.5, commission_rt=0.0)
sb.SPECS["USA30IDXUSD"] = sb.Spec(min_stop=15.0, max_stop=250.0, slip=1.0, commission_rt=0.0)

symbols = ["EURUSD", "USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD"]
bars = {}
for s in symbols:
    print(f"Loading {s}...", flush=True)
    raw = load_m1_symbol(s)
    bars[s] = sb.prepare(raw)

print("=" * 80, flush=True)
print("TESTING MULTI-ASSET MERGED SILVER BULLET (2021-2026)", flush=True)
print("=" * 80, flush=True)

all_dev = []
all_oos = []

for s in symbols:
    for win in ["AM", "PM"]:
        t_dev = sb.run_slot_c22(bars[s], s, win, "2021-01-01", "2024-12-31", cal_df)
        t_oos = sb.run_slot_c22(bars[s], s, win, "2025-01-01", "2026-12-31", cal_df)
        
        m_dev = compute_metrics(t_dev)
        m_oos = compute_metrics(t_oos)
        
        print(f"{s:14s} {win:3s} | DEV: n={m_dev['n']:3d} WR={m_dev['win_rate']*100:4.1f}% PF={m_dev['pf']:4.2f} MeanR={m_dev['mean_r']:+5.3f}R | OOS: n={m_oos['n']:3d} WR={m_oos['win_rate']*100:4.1f}% PF={m_oos['pf']:4.2f} MeanR={m_oos['mean_r']:+5.3f}R", flush=True)
        
        if not t_dev.empty:
            t_dev["slot"] = f"{s}_{win}"
            all_dev.append(t_dev)
        if not t_oos.empty:
            t_oos["slot"] = f"{s}_{win}"
            all_oos.append(t_oos)

dev_df = pd.concat(all_dev, ignore_index=True)
oos_df = pd.concat(all_oos, ignore_index=True)

m_dev_tot = compute_metrics(dev_df)
m_oos_tot = compute_metrics(oos_df)

print("=" * 80, flush=True)
print(f"TOTAL DEV (2021-2024): n={m_dev_tot['n']} | WR={m_dev_tot['win_rate']*100:.1f}% | PF={m_dev_tot['pf']:.2f} | MeanR={m_dev_tot['mean_r']:+.3f}R | MaxDD={m_dev_tot['max_dd_r']:.2f}R", flush=True)
print(f"TOTAL OOS (2025-2026): n={m_oos_tot['n']} | WR={m_oos_tot['win_rate']*100:.1f}% | PF={m_oos_tot['pf']:.2f} | MeanR={m_oos_tot['mean_r']:+.3f}R | MaxDD={m_oos_tot['max_dd_r']:.2f}R", flush=True)

# Full Statistical Rules Check
r_oos = oos_df["r"].to_numpy(np.float64)
sharpe = (r_oos.mean() / r_oos.std() * np.sqrt(252)) if r_oos.std() > 0 else 0.0
print(f"OOS Annualized Sharpe: {sharpe:.2f}", flush=True)

np.random.seed(42)
mc_pfs, mc_dds = [], []
n = len(r_oos)
for _ in range(1000):
    sample = np.random.choice(r_oos, size=n, replace=True)
    w = sample[sample > 0].sum()
    l = abs(sample[sample <= 0].sum())
    pf = w / l if l > 0 else 999.0
    mc_pfs.append(pf)
    eq = np.r_[0.0, np.cumsum(sample)]
    dd = float((np.maximum.accumulate(eq) - eq).max())
    mc_dds.append(dd)

p5_pf = np.percentile(mc_pfs, 5)
p95_dd = np.percentile(mc_dds, 95)
print(f"Monte Carlo 1000 runs -> 5th-pct PF: {p5_pf:.2f} | 95th-pct Max DD: {p95_dd:.2f} R", flush=True)
print("=" * 80, flush=True)
