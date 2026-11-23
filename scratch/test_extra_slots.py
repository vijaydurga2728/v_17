import sys
from pathlib import Path
import pandas as pd
REPO = Path('.').resolve()
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'scripts'))
from run_c22_silver_bullet import load_calendar_blackout_df, compute_metrics, load_m1_symbol
from v17.setups import c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

test_slots = [
    ('AM', 'USA30IDXUSD'),
    ('AM', 'USA500IDXUSD'),
    ('PM', 'XAUUSD'),
    ('LDN', 'XAUUSD'),
]

for win, sym in test_slots:
    try:
        b = sb.prepare(load_m1_symbol(sym))
        t_dev = sb.run_slot_c22(b, sym, win, '2021-01-01', '2024-12-31', cal_df)
        t_ho = sb.run_slot_c22(b, sym, win, '2025-01-01', '2026-12-31', cal_df)
        m_dev = compute_metrics(t_dev)
        m_ho = compute_metrics(t_ho)
        print(f"[{win:3s}] {sym:12s} | DEV n={m_dev['n']:2d} PF={m_dev['pf']:4.2f} WR={m_dev['win_rate']*100:4.1f}% | OOS n={m_ho['n']:2d} PF={m_ho['pf']:4.2f} WR={m_ho['win_rate']*100:4.1f}%", flush=True)
    except Exception as e:
        print(f"[{win:3s}] {sym:12s} -> {e}", flush=True)
