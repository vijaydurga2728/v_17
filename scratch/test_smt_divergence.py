"""SMT Divergence Quantitative Filter Audit.

Compares M5 swing highs/lows between USATECHIDXUSD (NQ), USA500IDXUSD (ES), and USA30IDXUSD (YM)
during the Open-Drive (09:30-10:30) and PM (14:00-15:00) windows.
Tests if requiring SMT Divergence filters out false breakouts and improves Profit Factor.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, compute_metrics, load_calendar_blackout_df
from v17.setups import c25_silver_bullet_institutional as c25

cal_df = load_calendar_blackout_df()

print("Loading indices for SMT Divergence Audit...", flush=True)
b_nq = c25.prepare(load_m1_symbol("USATECHIDXUSD"))
b_ym = c25.prepare(load_m1_symbol("USA30IDXUSD"))
b_es = c25.prepare(load_m1_symbol("USA500IDXUSD"))

m5_nq = c25.build_m5(b_nq)
m5_ym = c25.build_m5(b_ym)
m5_es = c25.build_m5(b_es)

print("Indices ready.", flush=True)

# Run USA30 Open-Drive and PM trades
for win in ["OPEN_DRIVE", "PM"]:
    print(f"\n{'='*70}\nEVALUATING SMT DIVERGENCE: USA30 [{win}]\n{'='*70}", flush=True)
    t_all = c25.run_slot_c25(b_ym, "USA30IDXUSD", win, "2021-01-01", "2026-12-31", cal_df)
    if t_all.empty:
        continue
        
    has_smt = []
    
    (sh, sm), (eh, em) = c25.WINDOWS[win]
    
    for _, row in t_all.iterrows():
        d = pd.Timestamp(row["day"]).date()
        d0_ns = pd.Timestamp(d).tz_localize(c25.NY).tz_convert("UTC").value
        ws_ns = d0_ns + (sh * 3600 + sm * 60) * 1_000_000_000
        we_ns = d0_ns + (eh * 3600 + em * 60) * 1_000_000_000
        
        # Find M5 slice in YM, NQ, ES
        i_ym_s = np.searchsorted(m5_ym.ts_start, ws_ns)
        i_ym_e = np.searchsorted(m5_ym.ts_close, we_ns)
        
        i_nq_s = np.searchsorted(m5_nq.ts_start, ws_ns)
        i_nq_e = np.searchsorted(m5_nq.ts_close, we_ns)
        
        i_es_s = np.searchsorted(m5_es.ts_start, ws_ns)
        i_es_e = np.searchsorted(m5_es.ts_close, we_ns)
        
        side = row["side"]
        
        # Check SMT divergence at window start vs window peak
        # In long trades: did NQ make a lower low while YM or ES made a higher low?
        if side == 1: # Bullish setup
            ym_min = np.min(m5_ym.l[i_ym_s:i_ym_e]) if i_ym_e > i_ym_s else 0
            nq_min = np.min(m5_nq.l[i_nq_s:i_nq_e]) if i_nq_e > i_nq_s else 0
            es_min = np.min(m5_es.l[i_es_s:i_es_e]) if i_es_e > i_es_s else 0
            
            # Check relative change from open
            ym_drop = (ym_min - m5_ym.o[i_ym_s]) / m5_ym.o[i_ym_s] if i_ym_s < len(m5_ym.o) else 0
            nq_drop = (nq_min - m5_nq.o[i_nq_s]) / m5_nq.o[i_nq_s] if i_nq_s < len(m5_nq.o) else 0
            es_drop = (es_min - m5_es.o[i_es_s]) / m5_es.o[i_es_s] if i_es_s < len(m5_es.o) else 0
            
            # Significant divergence in downward extension
            divergence = abs(nq_drop - ym_drop) > 0.0015 or abs(es_drop - ym_drop) > 0.0010
            has_smt.append(divergence)
        else: # Bearish setup
            ym_max = np.max(m5_ym.h[i_ym_s:i_ym_e]) if i_ym_e > i_ym_s else 0
            nq_max = np.max(m5_nq.h[i_nq_s:i_nq_e]) if i_nq_e > i_nq_s else 0
            es_max = np.max(m5_es.h[i_es_s:i_es_e]) if i_es_e > i_es_s else 0
            
            ym_rally = (ym_max - m5_ym.o[i_ym_s]) / m5_ym.o[i_ym_s] if i_ym_s < len(m5_ym.o) else 0
            nq_rally = (nq_max - m5_nq.o[i_nq_s]) / m5_nq.o[i_nq_s] if i_nq_s < len(m5_nq.o) else 0
            es_rally = (es_max - m5_es.o[i_es_s]) / m5_es.o[i_es_s] if i_es_s < len(m5_es.o) else 0
            
            divergence = abs(nq_rally - ym_rally) > 0.0015 or abs(es_rally - ym_rally) > 0.0010
            has_smt.append(divergence)
            
    t_all["has_smt"] = has_smt
    
    m_all = compute_metrics(t_all)
    m_smt = compute_metrics(t_all[t_all["has_smt"]])
    m_no_smt = compute_metrics(t_all[~t_all["has_smt"]])
    
    print(f"ALL TRADES:     n={m_all['n']:3d} | WR={m_all['win_rate']*100:4.1f}% | PF={m_all['pf']:4.2f} | MeanR={m_all['mean_r']:+6.3f}R | DD={m_all['max_dd_r']:4.1f}R", flush=True)
    print(f"WITH SMT DIV:   n={m_smt['n']:3d} | WR={m_smt['win_rate']*100:4.1f}% | PF={m_smt['pf']:4.2f} | MeanR={m_smt['mean_r']:+6.3f}R | DD={m_smt['max_dd_r']:4.1f}R", flush=True)
    print(f"WITHOUT SMT:    n={m_no_smt['n']:3d} | WR={m_no_smt['win_rate']*100:4.1f}% | PF={m_no_smt['pf']:4.2f} | MeanR={m_no_smt['mean_r']:+6.3f}R | DD={m_no_smt['max_dd_r']:4.1f}R", flush=True)
