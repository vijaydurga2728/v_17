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
print(f"Loaded {len(df):,} bars for {sym}")

# Baseline run
pre = precompute(df, sym)
loop = EventLoop(sym, [JudasSwing(), SilverBullet()], DefaultRiskEngine(), pre)
trades, equity = loop.run(START, END, Decimal("10000"))

print(f"\n=== EURGBP BASELINE TRADES ({len(trades)} trades) ===")
rows = []
for t in trades:
    # identify setup from signal_id or confluence
    dt = t.opened_at
    rows.append({
        "opened_at": str(t.opened_at),
        "side": t.side.value,
        "entry": float(t.entry),
        "sl": float(t.sl),
        "tp": float(t.tp),
        "pips_to_tp": round(abs(float(t.tp - t.entry)) / 0.0001, 1),
        "pips_to_sl": round(abs(float(t.entry - t.sl)) / 0.0001, 1),
        "close_price": float(t.close_price) if t.close_price else None,
        "pnl": float(t.pnl) if t.pnl is not None else 0.0,
        "reason": t.reason,
        "hour_utc": dt.hour,
    })

tdf = pd.DataFrame(rows)
print(tdf.to_string())

print("\n--- Breakdown by Exit Reason ---")
print(tdf.groupby("reason")["pnl"].agg(["count", "sum"]))

print("\n--- Breakdown by Hour (UTC) ---")
print(tdf.groupby("hour_utc")["pnl"].agg(["count", "sum"]))
