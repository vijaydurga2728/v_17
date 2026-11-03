"""Count trading days where snap.bias == NONE for 2015-2017 EUR/GBP.
If >70% of days are NONE, PDH/PDL + 4H confirmation is over-filtering.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime

import pandas as pd

from v17.backtest.precompute import precompute, snapshot_at
from v17.common.types import TF, Bias, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.setups.sessions import in_judas_window, in_silver_bullet_window

SYMBOL = Symbol(sys.argv[1] if len(sys.argv) > 1 else "EURUSD")
START = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=UTC) if len(sys.argv) > 2 else datetime(2015, 1, 1, tzinfo=UTC)
END = datetime.fromisoformat(sys.argv[3]).replace(tzinfo=UTC) if len(sys.argv) > 3 else datetime(2017, 12, 31, tzinfo=UTC)


def load_bars(symbol: Symbol, start: datetime, end: datetime) -> pd.DataFrame:
    s = get_settings()
    s.ensure_dirs()
    p = ParquetBarProvider(s.parquet_root)
    rows = [b.model_dump() for b in p.bars(symbol, TF.M1, start, end)]
    df = pd.DataFrame(rows)
    for col in ("open", "high", "low", "close", "spread_pips"):
        df[col] = df[col].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["volume"] = df["volume"].astype("int64")
    return df


def main() -> None:
    bars = load_bars(SYMBOL, START, END)
    pre = precompute(bars, SYMBOL)

    # Sample first killzone-eligible bar of each unique date and record bias.
    date_bias: dict[object, str] = {}
    for ts_val in bars["ts"]:
        ts = ts_val.to_pydatetime()
        if not (in_silver_bullet_window(ts) or in_judas_window(ts)):
            continue
        d = ts.date()
        if d in date_bias:
            continue
        snap = snapshot_at(pre, ts)
        date_bias[d] = snap.bias.name

    total = len(date_bias)
    counts: dict[str, int] = {"BULL": 0, "BEAR": 0, "NONE": 0}
    for b in date_bias.values():
        counts[b] = counts.get(b, 0) + 1
    print(f"{SYMBOL} {START.date()} to {END.date()}")
    print(f"total trading days with killzone bars: {total}")
    for k, v in counts.items():
        pct = (v / total * 100) if total else 0.0
        print(f"  {k:6s}: {v:4d}  ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
