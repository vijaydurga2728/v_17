"""NAS100 per-gate audit using the REAL silver_bullet code paths.
Replicates evaluate() step-by-step with correct per-symbol constants.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from v17.backtest.cost import (
    MIN_PIP_SL_BY_SYMBOL,
    TP_FALLBACK_PIPS_BY_SYMBOL,
    pip_size,
)
from v17.backtest.precompute import precompute, snapshot_at
from v17.common.types import TF, Bias, Side, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.setups.sessions import in_silver_bullet_window
from v17.setups.silver_bullet import (
    MSS_LOOKBACK_MIN,
    SWEEP_LOOKBACK_MIN,
    _pick_zone,
)
from v17.setups.targets import passes_rr, pip_distance, rr

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
    pip = pip_size(SYMBOL)
    tp_pips = TP_FALLBACK_PIPS_BY_SYMBOL.get(SYMBOL, Decimal("22"))
    min_sl = MIN_PIP_SL_BY_SYMBOL.get(SYMBOL, Decimal("2"))

    counts = {
        "in_window": 0,
        "bias_none": 0,
        "no_zone": 0,
        "no_sweep": 0,
        "no_mss": 0,
        "pip_sl_fail": 0,
        "rr_fail": 0,
        "signal": 0,
    }

    for i, ts_val in enumerate(df["ts"].iloc[:-1]):
        ts = ts_val.to_pydatetime()
        if not in_silver_bullet_window(ts):
            continue
        counts["in_window"] += 1
        snap = snapshot_at(pre, ts)
        if snap.bias == Bias.NONE:
            counts["bias_none"] += 1
            continue
        side = Side.BUY if snap.bias == Bias.BULL else Side.SELL
        last_close = Decimal(str(float(df["close"].iloc[i])))
        zone = _pick_zone(snap.zones, side, last_close, ts, SYMBOL)
        if zone is None:
            counts["no_zone"] += 1
            continue
        want_sweep = "ssl" if side == Side.BUY else "bsl"
        sweep_ok = any(
            sw.kind == want_sweep and (ts - sw.at) <= timedelta(minutes=SWEEP_LOOKBACK_MIN)
            for sw in snap.sweeps
        )
        if not sweep_ok:
            counts["no_sweep"] += 1
            continue
        mss_ok = any(
            sw.kind == "mss"
            and sw.side == side
            and sw.tf == TF.M1
            and (ts - sw.at) <= timedelta(minutes=MSS_LOOKBACK_MIN)
            for sw in snap.swings
        )
        if not mss_ok:
            counts["no_mss"] += 1
            continue
        entry = (zone.top + zone.bottom) / 2
        if side == Side.BUY:
            sl = zone.bottom - pip
            tp = entry + tp_pips * pip
        else:
            sl = zone.top + pip
            tp = entry - tp_pips * pip
        if pip_distance(entry, sl, symbol=SYMBOL) < min_sl:
            counts["pip_sl_fail"] += 1
            continue
        rr_val = rr(entry, sl, tp, side)
        if not passes_rr(rr_val):
            counts["rr_fail"] += 1
            continue
        counts["signal"] += 1

    print(f"NAS100 June 2024 SB gate audit (actual silver_bullet logic):")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
