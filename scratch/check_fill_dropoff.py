"""Analyze why setups do not get filled.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df
from v17.setups import c22_silver_bullet as sb

b_eur = sb.prepare(load_m1_symbol("EURUSD"))
m5 = sb.build_m5(b_eur)
ph5, pl5 = sb.pivot_flags(m5.h, m5.l, 2, 2)
daily_df = sb.build_daily_df(b_eur)
sp = sb.SPECS["EURUSD"]

(sh, sm), (eh, em) = sb.WINDOWS["AM"]
(end_h, end_m) = sb.SESSION_ENDS["AM"]

days = pd.date_range("2021-01-01", "2026-12-31", freq="B")

setups_found = 0
filled_exact = 0
invalidated_before_fill = 0
never_reached_entry = 0
missed_by_pips = []

for day in days:
    d = day.date()
    ctx = sb.compute_day_context(b_eur, d, "AM", daily_df)
    if ctx is None or ctx.dol_side == 0 or ctx.adr_exhausted: continue
    
    d0_ns = pd.Timestamp(d).tz_localize("America/New_York").tz_convert("UTC").value
    ws_ns = d0_ns + (sh * 3600 + sm * 60) * 1_000_000_000
    we_ns = d0_ns + (eh * 3600 + em * 60) * 1_000_000_000
    sess_end_ns = d0_ns + (end_h * 3600 + end_m * 60) * 1_000_000_000
    
    m5_start = int(np.searchsorted(m5.ts_start, ws_ns))
    m5_end = int(np.searchsorted(m5.ts_close, we_ns))
    if m5_end <= m5_start + 2: continue
    
    setup = sb.find_setup(m5, ph5, pl5, m5_start, m5_end, ctx, sp, 0.0001)
    if setup is None: continue
    
    setups_found += 1
    m1_start = setup.c3_close_m1 + 1
    m1_end = int(np.searchsorted(b_eur.ts, sess_end_ns)) - 1
    if m1_end <= m1_start: continue
    
    filled = False
    inval = False
    min_dist_to_entry = 999.0
    
    for m in range(m1_start, m1_end):
        if setup.side == 1:
            if b_eur.bid_l[m] <= setup.anchor_px:
                inval = True
                break
            dist = b_eur.ask_l[m] - setup.entry_px
            if dist < min_dist_to_entry: min_dist_to_entry = dist
            if b_eur.ask_l[m] <= setup.entry_px:
                filled = True
                break
        else:
            if b_eur.ask_h[m] >= setup.anchor_px:
                inval = True
                break
            dist = setup.entry_px - b_eur.bid_h[m]
            if dist < min_dist_to_entry: min_dist_to_entry = dist
            if b_eur.bid_h[m] >= setup.entry_px:
                filled = True
                break
                
    if filled:
        filled_exact += 1
    elif inval:
        invalidated_before_fill += 1
    else:
        never_reached_entry += 1
        missed_by_pips.append(min_dist_to_entry / 0.0001)

print(f"2021-2026 EURUSD AM Setups: {setups_found}")
print(f"  Filled Exact Limit: {filled_exact} ({filled_exact/setups_found*100:.1f}%)")
print(f"  Invalidated before fill: {invalidated_before_fill} ({invalidated_before_fill/setups_found*100:.1f}%)")
print(f"  Session ended without reach: {never_reached_entry} ({never_reached_entry/setups_found*100:.1f}%)")
if missed_by_pips:
    print(f"  Missed entry median pips: {np.median(missed_by_pips):.2f} pips")
