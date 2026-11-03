"""Deep-dive NAS100: inspect zone sizes vs price, bias, sweeps.
Finds why zero signals fire on index data.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from v17.backtest.cost import pip_size
from v17.backtest.precompute import precompute, snapshot_at
from v17.common.types import TF, Bias, Side, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.setups.sessions import in_judas_window, in_silver_bullet_window
from v17.setups.silver_bullet import _pick_zone, ZONE_TOLERANCE_PIPS

SYMBOL = Symbol("USATECHIDXUSD")
START = datetime(2024, 6, 1, tzinfo=UTC)
END = datetime(2024, 6, 30, tzinfo=UTC)


def main() -> None:
    s = get_settings()
    s.ensure_dirs()
    p = ParquetBarProvider(s.parquet_root)
    rows = [b.model_dump() for b in p.bars(SYMBOL, TF.M1, START, END)]
    df = pd.DataFrame(rows)
    for col in ("open", "high", "low", "close", "spread_pips"):
        df[col] = df[col].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["volume"] = df["volume"].astype("int64")

    pre = precompute(df, SYMBOL)
    print(f"NAS100 June 2024: {len(df)} bars")
    print(f"zones_15m: {len(pre.zones_15m)}, swings_4h: {len(pre.swings_4h)}, sweeps_15m: {len(pre.sweeps_15m)}")
    pip = pip_size(SYMBOL)
    tol = ZONE_TOLERANCE_PIPS * pip
    print(f"pip_size: {pip}, zone_tolerance: {tol} ({ZONE_TOLERANCE_PIPS} pips × {pip})")

    # Zone size distribution
    heights = [float(z.top - z.bottom) for z in pre.zones_15m]
    if heights:
        heights.sort()
        print(f"\nzone heights: min={heights[0]:.1f} med={heights[len(heights)//2]:.1f} max={heights[-1]:.1f}")

    # Side distribution
    buy_zones = sum(1 for z in pre.zones_15m if z.side == Side.BUY)
    sell_zones = sum(1 for z in pre.zones_15m if z.side == Side.SELL)
    print(f"zones by side: BUY={buy_zones} SELL={sell_zones}")

    # Walk SB window bars, count where _pick_zone finds something
    sb_bars = 0
    sb_bias_none = 0
    sb_bias_bull = 0
    sb_bias_bear = 0
    sb_pick_fires = 0
    sb_pick_fails = 0
    for i, ts_val in enumerate(df["ts"].iloc[:-1]):
        ts = ts_val.to_pydatetime()
        if not in_silver_bullet_window(ts):
            continue
        sb_bars += 1
        snap = snapshot_at(pre, ts)
        if snap.bias == Bias.NONE:
            sb_bias_none += 1
            continue
        if snap.bias == Bias.BULL:
            sb_bias_bull += 1
            side = Side.BUY
        else:
            sb_bias_bear += 1
            side = Side.SELL
        from decimal import Decimal as _D
        last_close = _D(str(float(df["close"].iloc[i])))
        zone = _pick_zone(snap.zones, side, last_close, ts, SYMBOL)
        if zone is None:
            sb_pick_fails += 1
        else:
            sb_pick_fires += 1

    print(f"\nSB window bars: {sb_bars}")
    print(f"  bias NONE: {sb_bias_none}")
    print(f"  bias BULL: {sb_bias_bull}")
    print(f"  bias BEAR: {sb_bias_bear}")
    print(f"  pick fails (no zone within tolerance): {sb_pick_fails}")
    print(f"  pick fires (zone found): {sb_pick_fires}")

    if sb_pick_fails > 0 and buy_zones > 0:
        # Pick a sample bar and show what zones exist vs price
        for i, ts_val in enumerate(df["ts"].iloc[:-1]):
            ts = ts_val.to_pydatetime()
            if not in_silver_bullet_window(ts):
                continue
            snap = snapshot_at(pre, ts)
            if snap.bias == Bias.NONE:
                continue
            price = float(df["close"].iloc[i])
            side = Side.BUY if snap.bias == Bias.BULL else Side.SELL
            matching = [z for z in snap.zones if z.side == side and z.mitigated_at is None]
            if matching:
                z = matching[0]
                print(f"\nSample bar {ts.isoformat()} price={price:.1f} side={side.value}")
                print(f"  first same-side unmitigated zone: top={float(z.top):.1f} bottom={float(z.bottom):.1f}")
                print(f"  distance: price-top={price - float(z.top):.1f} price-bottom={price - float(z.bottom):.1f}")
                print(f"  tolerance needed to include: {min(abs(price - float(z.top)), abs(price - float(z.bottom))):.1f}")
                break


if __name__ == "__main__":
    main()
