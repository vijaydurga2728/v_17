"""Why does _pick_zone fail at 50 pips tolerance? Inspect zone side distribution + price distances."""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from v17.backtest.precompute import precompute, snapshot_at
from v17.common.types import TF, Bias, Side, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.setups.sessions import in_silver_bullet_window
from v17.setups.silver_bullet import ZONE_TOLERANCE_PIPS, _PIP

SYMBOL = Symbol(sys.argv[1] if len(sys.argv) > 1 else "EURUSD")
START = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=UTC) if len(sys.argv) > 2 else datetime(2024, 6, 1, tzinfo=UTC)
END = datetime.fromisoformat(sys.argv[3]).replace(tzinfo=UTC) if len(sys.argv) > 3 else datetime(2024, 6, 30, tzinfo=UTC)


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
    tol = ZONE_TOLERANCE_PIPS * _PIP
    print(f"tolerance: {ZONE_TOLERANCE_PIPS} pips = {tol}")

    sample_times = []
    for i, ts_val in enumerate(bars["ts"]):
        ts = ts_val.to_pydatetime()
        if in_silver_bullet_window(ts):
            sample_times.append((i, ts))
    print(f"SB window bars: {len(sample_times)}")

    # Analyze a sample of 100 bars
    step = max(1, len(sample_times) // 100)
    sample = sample_times[::step]
    print(f"sampling {len(sample)} bars")

    hist = {"any_unmit": 0, "sell_unmit": 0, "buy_unmit": 0,
            "sell_within_tol": 0, "buy_within_tol": 0,
            "sell_nearest_pips": [], "buy_nearest_pips": []}

    for i, ts in sample:
        snap = snapshot_at(pre, ts)
        last_close = Decimal(str(float(bars["close"].iloc[i])))
        unmit = [z for z in snap.zones if z.mitigated_at is None]
        hist["any_unmit"] += len(unmit)
        for z in unmit:
            if z.side == Side.SELL:
                hist["sell_unmit"] += 1
                if z.bottom - tol <= last_close <= z.top + tol:
                    hist["sell_within_tol"] += 1
                if last_close < z.bottom:
                    d = float(z.bottom - last_close) / float(_PIP)
                elif last_close > z.top:
                    d = float(last_close - z.top) / float(_PIP)
                else:
                    d = 0.0
                hist["sell_nearest_pips"].append(d)
            else:
                hist["buy_unmit"] += 1
                if z.bottom - tol <= last_close <= z.top + tol:
                    hist["buy_within_tol"] += 1
                if last_close < z.bottom:
                    d = float(z.bottom - last_close) / float(_PIP)
                elif last_close > z.top:
                    d = float(last_close - z.top) / float(_PIP)
                else:
                    d = 0.0
                hist["buy_nearest_pips"].append(d)

    print(f"total unmitigated zones across sample: {hist['any_unmit']}")
    print(f"  sell: {hist['sell_unmit']}, within_tol: {hist['sell_within_tol']}")
    print(f"  buy:  {hist['buy_unmit']}, within_tol: {hist['buy_within_tol']}")
    if hist["sell_nearest_pips"]:
        s = sorted(hist["sell_nearest_pips"])
        print(f"  sell nearest pips: min={s[0]:.1f} med={s[len(s)//2]:.1f} max={s[-1]:.1f}")
    if hist["buy_nearest_pips"]:
        b = sorted(hist["buy_nearest_pips"])
        print(f"  buy nearest pips: min={b[0]:.1f} med={b[len(b)//2]:.1f} max={b[-1]:.1f}")


if __name__ == "__main__":
    main()
