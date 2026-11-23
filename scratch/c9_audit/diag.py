import numpy as np, pandas as pd
from v17.backtest.c9_runner import load_m1
m1 = load_m1("dev")
t = pd.to_datetime(m1.ts_utc, unit="ns", utc=True).dt.tz_convert("America/New_York")
# (a) timestamp convention: activity by local minute around open/close (spread proxy + count)
hm = t.dt.strftime("%H:%M"); sp = (m1.ask_c - m1.bid_c)
g = pd.DataFrame({"hm": hm, "sp": sp, "rng": m1.bid_h - m1.bid_l}).groupby("hm").agg(n=("sp","size"), spread=("sp","median"), range=("rng","median"))
print("(a) per-minute median 1m range & spread around RTH open/close:")
print(g.reindex(["09:25","09:28","09:29","09:30","09:31","09:32","15:58","15:59","16:00","16:01","16:15","17:00","18:00"]).round(2).to_string())
# (b) integrity
print("\n(b) bid>ask rows:", int((m1.bid_c > m1.ask_c).sum()), "| h<l rows:", int((m1.bid_h < m1.bid_l).sum()),
      "| o/c outside h/l:", int(((m1.bid_o > m1.bid_h) | (m1.bid_o < m1.bid_l) | (m1.bid_c > m1.bid_h) | (m1.bid_c < m1.bid_l)).sum()))
print("    median spread pts:", float(sp.median()), " p99:", float(sp.quantile(.99)), " max:", float(sp.max()))
r = np.log(((m1.bid_c+m1.ask_c)/2)).diff().abs()
print("    1m |logret| > 2%:", int((r > 0.02).sum()))
# (c) trade anatomy for 3 slots
for sid in ["buf0.00_long_only_n1", "buf0.05_long_only_n2", "buf0.00_short_only_n2"]:
    tl = pd.read_parquet(f"out/c9/trades/{sid}.parquet")
    sd = (tl.entry_px - tl.stop).abs()
    print(f"\n(c) {sid}: n={len(tl)}")
    print("   exit reasons:", tl.exit_reason.value_counts().to_dict())
    print("   mean R by reason:", tl.groupby("exit_reason").r.mean().round(2).to_dict())
    print(f"   stop dist pts median {sd.median():.1f} | rr_at_entry median {tl.rr_at_entry.median():.2f} | rr<=0 {int((tl.rr_at_entry<=0).sum())}")
    print(f"   win {(tl.r>0).mean():.3f} avg win {tl.r[tl.r>0].mean():.2f} avg loss {tl.r[tl.r<0].mean():.2f}")
    print("   by year total R:", tl.groupby(pd.to_datetime(tl.date).dt.year).r.sum().round(1).to_dict())
