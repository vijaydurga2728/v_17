"""Patch the runner's regime->direction mapping: SPX LONG_BIAS -> go SHORT FX,
SPX SHORT_BIAS -> go LONG FX. Monkey-patch via signal_override is insufficient
since the runner reads reg_state separately. Patch compute_regime output instead:
swap LONG_BIAS <-> SHORT_BIAS."""
import pandas as pd, pyarrow.parquet as pq
from pathlib import Path
from v17.backtest import c6_position
from v17.backtest import c6_runner
from v17.setups import c6_regime

root = Path(r"C:/personal/v_17"); m5 = root / "data" / "bars_m5"


def load(sym):
    frames = []
    for yr in range(2015, 2024):
        for p in sorted((m5 / sym / f"year={yr}").glob("*.parquet")):
            frames.append(pq.read_table(p).to_pandas())
    return pd.concat(frames, ignore_index=True).sort_values("ts_utc").reset_index(drop=True)


# Monkey-patch compute_regime to SWAP long<->short labels.
_orig = c6_regime.compute_regime
def swapped_regime(*a, **kw):
    df = _orig(*a, **kw)
    s = df["regime_state"].copy()
    df.loc[s == "LONG_BIAS", "regime_state"] = "__TMP__"
    df.loc[s == "SHORT_BIAS", "regime_state"] = "LONG_BIAS"
    df.loc[s == "__TMP__", "regime_state"] = "SHORT_BIAS"
    return df
c6_runner.compute_regime = swapped_regime

print("loading...")
spx = load("USA500IDXUSD"); aud = load("AUDUSD"); jpy = load("USDJPY")
cal = pq.read_table(root / "data/calendar_cache/ff_c6_index.parquet").to_pandas()

c6_position.LEG_A_TARGET_R_MULT = 1.0
c6_position.TRAIL_FROM_ENTRY = True  # V3 trail-only; fewer assumptions
params = {"K": 0.3, "slope_window": 12, "C": 0.4}

print(f"\n{'year':<6}{'trades':>8}{'net':>12}{'WR':>8}{'PF':>8}  L_net   S_net")
for yr in range(2015, 2024):
    s = pd.Timestamp(f"{yr}-01-01", tz="UTC").value
    e = pd.Timestamp(f"{yr}-12-31", tz="UTC").value
    tl, _ = c6_runner.run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10000.0, s, e)
    if len(tl) == 0:
        print(f"{yr:<6}{'0':>8}"); continue
    wins = tl[tl["net_pnl_usd"] > 0]["net_pnl_usd"]
    losses = tl[tl["net_pnl_usd"] < 0]["net_pnl_usd"]
    pf = wins.sum() / (-losses.sum()) if len(losses) else float("inf")
    long_net = tl[tl.side == "long"]["net_pnl_usd"].sum()
    short_net = tl[tl.side == "short"]["net_pnl_usd"].sum()
    print(f"{yr:<6}{len(tl):>8}{tl['net_pnl_usd'].sum():>12.0f}{(tl['net_pnl_usd']>0).mean():>8.3f}"
          f"{pf:>8.3f}  L:{long_net:>6.0f} S:{short_net:>6.0f}")
