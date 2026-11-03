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
from v17.backtest import cost

s = get_settings()
START = datetime(2015, 1, 1, tzinfo=UTC)
END = datetime(2017, 12, 31, tzinfo=UTC)
sym = Symbol("EURGBP")

df = read_1m(sym, START, END, s.parquet_root)
pre = precompute(df, sym)

cost.TP_FALLBACK_PIPS_BY_SYMBOL["EURGBP"] = Decimal("14")

loop = EventLoop(sym, [JudasSwing(), SilverBullet()], DefaultRiskEngine(), pre)
trades, equity = loop.run(START, END, Decimal("10000"))

rows = []
for t in trades:
    rows.append({
        "opened_at": str(t.opened_at),
        "setup": "judas" if "judas" in t.signal_id else "silver_bullet",
        "side": t.side.value,
        "entry": float(t.entry),
        "sl": float(t.sl),
        "tp": float(t.tp),
        "pips_sl": round(abs(float(t.entry - t.sl)) / 0.0001, 1),
        "reason": t.reason,
        "pnl": float(t.pnl) if t.pnl is not None else 0.0,
        "hour_utc": t.opened_at.hour,
    })

tdf = pd.DataFrame(rows)
print(f"Total trades: {len(tdf)}")
print(f"Win Rate: {len(tdf[tdf['pnl'] > 0]) / len(tdf) * 100:.1f}%")
print(f"Net PnL: ${tdf['pnl'].sum():+.2f}")
print(f"Max DD: {loop.max_floating_dd_pct:.2f}%")
print("\n--- By Setup ---")
print(tdf.groupby("setup")["pnl"].agg(["count", lambda x: (x > 0).mean() * 100, "sum"]).rename(columns={"<lambda_0>": "WR%"}))
print("\n--- By Hour UTC ---")
print(tdf.groupby("hour_utc")["pnl"].agg(["count", lambda x: (x > 0).mean() * 100, "sum"]).rename(columns={"<lambda_0>": "WR%"}))
