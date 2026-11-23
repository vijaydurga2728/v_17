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

print("=" * 80, flush=True)
print("EVALUATING UPGRADED SILVER BULLET ENGINE (DEV vs OOS)", flush=True)
print("=" * 80, flush=True)

test_slots = [
    ("EURUSD", "AM"),
    ("USATECHIDXUSD", "AM"),
    ("USATECHIDXUSD", "PM"),
    ("USA500IDXUSD", "AM"),
]

dev_trades = []
oos_trades = []

for sym, win in test_slots:
    print(f"Loading {sym}...", flush=True)
    raw = load_m1_symbol(sym)
    b = sb.prepare(raw)
    
    t_dev = sb.run_slot_c22(b, sym, win, "2021-01-01", "2024-12-31", cal_df)
    t_oos = sb.run_slot_c22(b, sym, win, "2025-01-01", "2026-12-31", cal_df)
    
    m_dev = compute_metrics(t_dev)
    m_oos = compute_metrics(t_oos)
    
    print(f"[{sym:14s} {win:3s}] DEV (2021-2024): n={m_dev['n']:3d} | WR={m_dev['win_rate']*100:4.1f}% | PF={m_dev['pf']:5.2f} | MeanR={m_dev['mean_r']:+5.3f}R | MaxDD={m_dev['max_dd_r']:4.1f}R", flush=True)
    print(f"[{sym:14s} {win:3s}] OOS (2025-2026): n={m_oos['n']:3d} | WR={m_oos['win_rate']*100:4.1f}% | PF={m_oos['pf']:5.2f} | MeanR={m_oos['mean_r']:+5.3f}R | MaxDD={m_oos['max_dd_r']:4.1f}R", flush=True)
    
    if not t_dev.empty:
        t_dev["slot"] = f"{sym}_{win}"
        dev_trades.append(t_dev)
    if not t_oos.empty:
        t_oos["slot"] = f"{sym}_{win}"
        oos_trades.append(t_oos)

print("=" * 80, flush=True)
if dev_trades:
    all_dev = pd.concat(dev_trades, ignore_index=True)
    m_all_dev = compute_metrics(all_dev)
    print(f"PORTFOLIO DEV (2021-2024): n={m_all_dev['n']} | WR={m_all_dev['win_rate']*100:.1f}% | PF={m_all_dev['pf']:.2f} | MeanR={m_all_dev['mean_r']:+.3f}R | MaxDD={m_all_dev['max_dd_r']:.2f}R", flush=True)

if oos_trades:
    all_oos = pd.concat(oos_trades, ignore_index=True)
    m_all_oos = compute_metrics(all_oos)
    print(f"PORTFOLIO OOS (2025-2026): n={m_all_oos['n']} | WR={m_all_oos['win_rate']*100:.1f}% | PF={m_all_oos['pf']:.2f} | MeanR={m_all_oos['mean_r']:+.3f}R | MaxDD={m_all_oos['max_dd_r']:.2f}R", flush=True)

# Also check 12-fold walkforward and Monte Carlo stats
if oos_trades and len(all_oos) > 0:
    r = all_oos["r"].to_numpy(np.float64)
    # Sharpe ratio on R
    sharpe = (r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
    print(f"OOS Annualized Sharpe: {sharpe:.2f}", flush=True)
    
    # 1000-run Monte Carlo Bootstrap
    np.random.seed(42)
    mc_pfs = []
    mc_dds = []
    n = len(r)
    for _ in range(1000):
        sample = np.random.choice(r, size=n, replace=True)
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
