"""Compare three exit variants on 2022 slice."""
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
from v17.backtest import c6_position
from v17.backtest.c6_runner import run_backtest

root = Path(r"C:/personal/v_17")
m5 = root / "data" / "bars_m5"


def load(sym):
    frames = []
    for yr in range(2015, 2024):
        d = m5 / sym / f"year={yr}"
        for p in sorted(d.glob("*.parquet")):
            frames.append(pq.read_table(p).to_pandas())
    return pd.concat(frames, ignore_index=True).sort_values("ts_utc").reset_index(drop=True)


print("loading...")
spx = load("USA500IDXUSD"); aud = load("AUDUSD"); jpy = load("USDJPY")
cal = pq.read_table(root / "data/calendar_cache/ff_c6_index.parquet").to_pandas()
start = pd.Timestamp("2022-01-01", tz="UTC").value
end = pd.Timestamp("2022-12-31", tz="UTC").value
params = {"K": 0.3, "slope_window": 12, "C": 0.4}


def run_variant(name, target_mult, trail_from_entry):
    c6_position.LEG_A_TARGET_R_MULT = target_mult
    c6_position.TRAIL_FROM_ENTRY = trail_from_entry
    tl, _ = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params,
                          10000.0, start, end)
    if len(tl) == 0:
        print(f"{name}: no trades")
        return
    wins = tl[tl["net_pnl_usd"] > 0]["net_pnl_usd"]
    losses = tl[tl["net_pnl_usd"] < 0]["net_pnl_usd"]
    pf = wins.sum() / (-losses.sum()) if len(losses) else float("inf")
    print(f"\n=== {name} ===")
    print(f"trades={len(tl)}  net=${tl['net_pnl_usd'].sum():.2f}  WR={(tl['net_pnl_usd']>0).mean():.3f}  "
          f"avg_win=${wins.mean():.2f}  avg_loss=${losses.mean():.2f}  PF={pf:.3f}")
    print("  by side:")
    print(tl.groupby("side")["net_pnl_usd"].agg(["count", "sum", "mean"]).to_string())
    print("  leg A reasons:", dict(tl["leg_a_reason"].value_counts()))
    print("  leg B reasons:", dict(tl["leg_b_reason"].value_counts()))


run_variant("V1 baseline 1R/split/trail",  target_mult=1.0, trail_from_entry=False)
run_variant("V2 2R target/split/trail",    target_mult=2.0, trail_from_entry=False)
run_variant("V3 trail-only (no target)",   target_mult=1.0, trail_from_entry=True)
