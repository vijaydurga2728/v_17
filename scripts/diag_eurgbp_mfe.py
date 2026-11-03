from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd
from v17.common.types import Symbol
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.setups.judas_swing import JudasSwing
from v17.data.parquet_store import read_1m
from v17.config import get_settings

s = get_settings()
START = datetime(2015, 1, 1, tzinfo=UTC)
END = datetime(2017, 12, 31, tzinfo=UTC)
sym = Symbol("EURGBP")

df = read_1m(sym, START, END, s.parquet_root)
pre = precompute(df, sym)
loop = EventLoop(sym, [JudasSwing(), SilverBullet()], DefaultRiskEngine(), pre)
trades, equity = loop.run(START, END, Decimal("10000"))

# Calculate MFE for each trade
df_indexed = df.set_index("ts")

results = []
for t in trades:
    # slice bars between opened_at and closed_at
    sub = df_indexed.loc[t.opened_at : t.closed_at]
    entry = float(t.entry)
    sl = float(t.sl)
    tp = float(t.tp)
    side = t.side.value
    
    if side == "buy":
        max_favorable = sub["high"].max() - entry
        max_adverse = entry - sub["low"].min()
    else:
        max_favorable = entry - sub["low"].min()
        max_adverse = sub["high"].max() - entry
        
    mfe_pips = round(max_favorable / 0.0001, 1)
    mae_pips = round(max_adverse / 0.0001, 1)
    sl_pips = round(abs(entry - sl) / 0.0001, 1)
    
    results.append({
        "opened_at": str(t.opened_at),
        "setup": t.signal_id[:4],
        "side": side,
        "sl_pips": sl_pips,
        "mfe_pips": mfe_pips,
        "mae_pips": mae_pips,
        "reason": t.reason,
        "pnl": float(t.pnl) if t.pnl else 0.0,
    })

res_df = pd.DataFrame(results)
print(res_df.to_string())

print("\n--- MFE Stats for Losing Trades ---")
losses = res_df[res_df["reason"] == "sl"]
print(f"Mean MFE on losses: {losses['mfe_pips'].mean():.1f} pips")
print(f"Median MFE on losses: {losses['mfe_pips'].median():.1f} pips")
print(f"Losses with MFE >= 8 pips: {len(losses[losses['mfe_pips'] >= 8])} / {len(losses)}")
print(f"Losses with MFE >= 10 pips: {len(losses[losses['mfe_pips'] >= 10])} / {len(losses)}")
print(f"Losses with MFE >= 12 pips: {len(losses[losses['mfe_pips'] >= 12])} / {len(losses)}")
print(f"Losses with MFE >= 15 pips: {len(losses[losses['mfe_pips'] >= 15])} / {len(losses)}")
