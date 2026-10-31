"""Diagnose where silver_bullet + judas drop candidates. Counts per-gate rejections over N days."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from v17.backtest.precompute import precompute, snapshot_at
from v17.common.types import TF, Bias, Side, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.setups.judas_swing import JudasSwing
from v17.setups.sessions import in_judas_window, in_silver_bullet_window
from v17.setups.silver_bullet import SilverBullet, _pick_zone

import sys

if len(sys.argv) >= 4:
    SYMBOL = Symbol(sys.argv[1])
    START = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=UTC)
    END = datetime.fromisoformat(sys.argv[3]).replace(tzinfo=UTC)
else:
    SYMBOL = Symbol("EURUSD")
    START = datetime(2024, 6, 1, tzinfo=UTC)
    END = datetime(2024, 6, 30, tzinfo=UTC)


def load_bars_1m(symbol: Symbol, start: datetime, end: datetime) -> pd.DataFrame:
    s = get_settings()
    s.ensure_dirs()
    p = ParquetBarProvider(s.parquet_root)
    rows = [b.model_dump() for b in p.bars(symbol, TF.M1, start, end)]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("open", "high", "low", "close", "spread_pips"):
        df[col] = df[col].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["volume"] = df["volume"].astype("int64")
    return df


def main() -> None:
    bars = load_bars_1m(SYMBOL, START, END)
    print(f"bars: {len(bars)}")
    if bars.empty:
        return
    pre = precompute(bars, SYMBOL)
    print(f"pre.choches_1m: {len(pre.choches_1m)}")
    print(f"pre.zones_15m: {len(pre.zones_15m)}")
    print(f"pre.swings_4h: {len(pre.swings_4h)}")
    print(f"pre.bars_4h: {len(pre.bars_4h)}")
    # Try with lower swing_length
    from v17.structure.swings import detect_swings
    for sl in (3, 5, 10):
        n = len(detect_swings(pre.bars_4h, TF.H4, swing_length=sl))
        print(f"  swings_4h at swing_length={sl}: {n}")
    print(f"pre.sweeps_15m: {len(pre.sweeps_15m)}")
    if pre.choches_1m:
        sides = {}
        for c in pre.choches_1m:
            sides[c.side] = sides.get(c.side, 0) + 1
        print(f"  choches by side: {sides}")
        print(f"  first choch: at={pre.choches_1m[0].at} side={pre.choches_1m[0].side}")

    # Setup gate counters
    stats = {
        "total_bars": 0,
        "sb_in_window": 0, "sb_bias_none": 0, "sb_no_zone": 0,
        "sb_no_sweep": 0, "sb_no_mss": 0, "sb_pip_sl_fail": 0, "sb_rr_fail": 0,
        "sb_signal": 0,
        "jd_in_window": 0, "jd_signal": 0,
        "snap_bias_bull": 0, "snap_bias_bear": 0, "snap_bias_none": 0,
        "snap_zones_total": 0, "snap_sweeps_total": 0, "snap_swings_mss": 0,
    }

    sb = SilverBullet()
    jd = JudasSwing()

    from v17.setups.sessions import JUDAS_START as _, SB_START as _2  # ensure import

    # Walk SB window bars (3-4 NY)
    for i in range(len(bars) - 1):
        ts = bars["ts"].iloc[i].to_pydatetime()
        stats["total_bars"] += 1

        if not in_silver_bullet_window(ts) and not in_judas_window(ts):
            continue

        snap = snapshot_at(pre, ts)
        if snap.bias == Bias.BULL:
            stats["snap_bias_bull"] += 1
        elif snap.bias == Bias.BEAR:
            stats["snap_bias_bear"] += 1
        else:
            stats["snap_bias_none"] += 1
        stats["snap_zones_total"] += len(snap.zones)
        stats["snap_sweeps_total"] += len(snap.sweeps)
        stats["snap_swings_mss"] += sum(1 for s in snap.swings if s.kind == "mss")

        if in_silver_bullet_window(ts):
            stats["sb_in_window"] += 1
            # Mirror SB.evaluate gate order
            if snap.bias == Bias.NONE:
                stats["sb_bias_none"] += 1
                continue
            side = Side.BUY if snap.bias == Bias.BULL else Side.SELL
            last_close = Decimal(str(float(bars["close"].iloc[i])))
            zone = _pick_zone(snap.zones, side, last_close)
            if zone is None:
                stats["sb_no_zone"] += 1
                continue
            want = "ssl" if side == Side.BUY else "bsl"
            sweep_ok = any(
                s.kind == want and (ts - s.at) <= timedelta(minutes=120)
                for s in snap.sweeps
            )
            if not sweep_ok:
                stats["sb_no_sweep"] += 1
                continue
            mss_ok = any(
                sw.kind == "mss" and sw.side == side and sw.tf == TF.M1
                and (ts - sw.at) <= timedelta(minutes=10)
                for sw in snap.swings
            )
            if not mss_ok:
                stats["sb_no_mss"] += 1
                continue
            # If we got here, we would have evaluated full SB; call it to check RR/SL
            sig = sb.evaluate(snap, ts, bars.iloc[: i + 1])
            if sig is None:
                stats["sb_pip_sl_fail"] += 1  # or rr; collapse
            else:
                stats["sb_signal"] += 1

        if in_judas_window(ts):
            stats["jd_in_window"] += 1
            sig = jd.evaluate(snap, ts, bars.iloc[: i + 1])
            if sig is not None:
                stats["jd_signal"] += 1

    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
