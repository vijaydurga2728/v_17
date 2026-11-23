"""Invert signal direction: LONG_BIAS -> go SHORT, SHORT_BIAS -> go LONG.
If this flips PnL positive, the regime-direction mapping is inverted somewhere.
Uses signal_override hook in run_backtest."""
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

# baseline exit (not V3)
c6_position.LEG_A_TARGET_R_MULT = 1.0
c6_position.TRAIL_FROM_ENTRY = False
params = {"K": 0.3, "slope_window": 12, "C": 0.4}


def invert_signals(sym, df):
    """Swap confirm_long <-> confirm_short. Also need regime inversion done separately."""
    out = df.copy()
    out["confirm_long"], out["confirm_short"] = df["confirm_short"].copy(), df["confirm_long"].copy()
    return out


# RUN 1: baseline directional mapping
start = pd.Timestamp("2022-01-01", tz="UTC").value
end = pd.Timestamp("2022-12-31", tz="UTC").value
tl_base, _ = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10000.0, start, end)

# RUN 2: inverted confirm (so LONG_BIAS + confirm_short entry = short the FX, mimicking inversion)
tl_inv, _ = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10000.0, start, end,
                           signal_override=invert_signals)

for name, tl in [("baseline", tl_base), ("inverted", tl_inv)]:
    if len(tl) == 0:
        print(f"{name}: no trades"); continue
    wins = tl[tl["net_pnl_usd"] > 0]["net_pnl_usd"]
    losses = tl[tl["net_pnl_usd"] < 0]["net_pnl_usd"]
    pf = wins.sum() / (-losses.sum()) if len(losses) else float("inf")
    print(f"\n=== {name} ===")
    print(f"trades={len(tl)}  net=${tl['net_pnl_usd'].sum():.0f}  WR={(tl['net_pnl_usd']>0).mean():.3f}  "
          f"avg_win=${wins.mean():.2f}  avg_loss=${losses.mean():.2f}  PF={pf:.3f}")
    print(tl.groupby(["regime_at_entry", "side"])["net_pnl_usd"].agg(["count", "sum"]).to_string())
