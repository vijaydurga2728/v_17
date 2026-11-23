import sys, time, numpy as np, pandas as pd
sys.path.insert(0, "scratch/c9_audit")
import ref_impl as ref
from v17.backtest.c9_runner import load_m1, prepare, run_slot
from v17.setups.c9_pdh_pdl import all_slots
m1 = load_m1("dev"); prep = prepare(m1, "dev")
t = time.time(); agg, fulldays = ref.m15_from_m1(m1); print(f"ref M15 bars {len(agg)} vs main {len(prep.sess.bins)} ({time.time()-t:.0f}s)")
# bar-level check
main_mid_c = prep.sess["mid_c"]; print("M15 mid_c max abs diff:", float(np.abs(agg.mc.to_numpy() - main_mid_c).max()))
for s in all_slots():
    a = run_slot(prep, s).reset_index(drop=True)
    b = ref.run(agg, fulldays, s.sweep_buffer, "long" if s.direction == "long_only" else "short", s.n_conf)
    same_n = len(a) == len(b)
    if same_n and len(a):
        dd = (pd.to_datetime(a.date).dt.date.to_numpy() == b.date.to_numpy()).all()
        dr = float(np.abs(a.r.to_numpy() - b.r.to_numpy()).max())
        rs = (a.exit_reason.to_numpy() == b.exit_reason.to_numpy()).all()
    else: dd = dr = rs = None
    print(f"{s.slot_id:24s} main {len(a):4d} ref {len(b):4d} dates_eq {dd} reasons_eq {rs} max|dR| {dr}")
