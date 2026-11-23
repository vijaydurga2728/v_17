"""Run V3 (trail-only) across full dev 2015-2023, per year."""
import pandas as pd, pyarrow.parquet as pq
from pathlib import Path
from v17.backtest import c6_position
from v17.backtest.c6_runner import run_backtest

root = Path(r"C:/personal/v_17"); m5 = root / "data" / "bars_m5"


def load(sym):
    frames = []
    for yr in range(2015, 2024):
        for p in sorted((m5 / sym / f"year={yr}").glob("*.parquet")):
            frames.append(pq.read_table(p).to_pandas())
    return pd.concat(frames, ignore_index=True).sort_values("ts_utc").reset_index(drop=True)


print("loading...")
spx = load("USA500IDXUSD"); aud = load("AUDUSD"); jpy = load("USDJPY")
cal = pq.read_table(root / "data/calendar_cache/ff_c6_index.parquet").to_pandas()

c6_position.LEG_A_TARGET_R_MULT = 1.0
c6_position.TRAIL_FROM_ENTRY = True
params = {"K": 0.3, "slope_window": 12, "C": 0.4}

print(f"\n{'year':<6}{'trades':>8}{'net':>12}{'WR':>8}{'avg_win':>10}{'avg_loss':>12}{'PF':>8}  by-side (long/short net)")
all_rows = []
for yr in range(2015, 2024):
    s = pd.Timestamp(f"{yr}-01-01", tz="UTC").value
    e = pd.Timestamp(f"{yr}-12-31", tz="UTC").value
    tl, _ = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10000.0, s, e)
    if len(tl) == 0:
        print(f"{yr:<6}{'0':>8}"); continue
    wins = tl[tl["net_pnl_usd"] > 0]["net_pnl_usd"]
    losses = tl[tl["net_pnl_usd"] < 0]["net_pnl_usd"]
    pf = wins.sum() / (-losses.sum()) if len(losses) else float("inf")
    long_net = tl[tl.side == "long"]["net_pnl_usd"].sum()
    short_net = tl[tl.side == "short"]["net_pnl_usd"].sum()
    print(f"{yr:<6}{len(tl):>8}{tl['net_pnl_usd'].sum():>12.0f}{(tl['net_pnl_usd']>0).mean():>8.3f}"
          f"{wins.mean():>10.2f}{losses.mean() if len(losses) else 0:>12.2f}{pf:>8.3f}"
          f"  L:{long_net:>7.0f} S:{short_net:>7.0f}")
    all_rows.append(tl)

print("\n--- TOTAL ---")
if all_rows:
    tot = pd.concat(all_rows, ignore_index=True)
    wins = tot[tot["net_pnl_usd"] > 0]["net_pnl_usd"]; losses = tot[tot["net_pnl_usd"] < 0]["net_pnl_usd"]
    pf = wins.sum() / (-losses.sum()) if len(losses) else float("inf")
    print(f"trades={len(tot)}  net=${tot['net_pnl_usd'].sum():.0f}  WR={(tot['net_pnl_usd']>0).mean():.3f}  "
          f"avg_win=${wins.mean():.2f}  avg_loss=${losses.mean():.2f}  PF={pf:.3f}")
