"""Trace actual silver_bullet signals through loop.py guards for NAS100.
Reveals where the 27 signals/month die inside the EventLoop.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from v17.backtest.cost import PIP_SCALE, ZONE_TOLERANCE_BY_SYMBOL
from v17.backtest.fills import entry_fill
from v17.backtest.precompute import precompute, snapshot_at
from v17.common.types import TF, Side, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.setups.silver_bullet import SilverBullet
from v17.setups.sessions import in_silver_bullet_window

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
    df = df.reset_index(drop=True)
    pre = precompute(df, SYMBOL)
    sb = SilverBullet()

    pip_scale = Decimal(PIP_SCALE.get(SYMBOL, 10000))
    slip_cap = ZONE_TOLERANCE_BY_SYMBOL.get(SYMBOL, Decimal("10"))

    counts = {
        "signals_from_evaluate": 0,
        "guard1_wrong_side_sl": 0,
        "guard2_slip_too_big": 0,
        "guard3_rr_fail": 0,
        "guard3_actual_risk_zero": 0,
        "fired_today_blocked": 0,
        "passes_all_guards": 0,
    }
    fired_today: set[tuple[str, Side]] = set()
    prev_date = None
    slip_samples: list[float] = []

    for i in range(len(df) - 1):
        ts = df["ts"].iloc[i].to_pydatetime()
        if not in_silver_bullet_window(ts):
            continue
        cur_date = ts.date()
        if prev_date is not None and cur_date != prev_date:
            fired_today = set()
        prev_date = cur_date

        snap = snapshot_at(pre, ts)
        recent = df.iloc[max(0, i - 1440) : i + 1]
        sig = sb.evaluate(snap, ts, recent)
        if sig is None:
            continue
        counts["signals_from_evaluate"] += 1

        if (sig.setup, sig.side) in fired_today:
            counts["fired_today_blocked"] += 1
            continue

        next_bar = df.iloc[i + 1]
        entry = entry_fill(sig.side, Decimal(str(float(next_bar["open"]))), SYMBOL)

        if sig.side == Side.SELL and entry >= sig.sl:
            counts["guard1_wrong_side_sl"] += 1
            continue
        if sig.side == Side.BUY and entry <= sig.sl:
            counts["guard1_wrong_side_sl"] += 1
            continue

        slip_pips = abs(entry - sig.entry) * pip_scale
        slip_samples.append(float(slip_pips))
        if slip_pips > slip_cap:
            counts["guard2_slip_too_big"] += 1
            continue

        if sig.side == Side.SELL:
            actual_risk = (sig.sl - entry) * pip_scale
            actual_reward = (entry - sig.tp) * pip_scale
        else:
            actual_risk = (entry - sig.sl) * pip_scale
            actual_reward = (sig.tp - entry) * pip_scale
        if actual_risk <= 0:
            counts["guard3_actual_risk_zero"] += 1
            continue
        if actual_reward / actual_risk < Decimal("1.5"):
            counts["guard3_rr_fail"] += 1
            continue

        counts["passes_all_guards"] += 1
        fired_today.add((sig.setup, sig.side))

    print(f"NAS100 June 2024 loop-level audit:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    if slip_samples:
        slip_samples.sort()
        n = len(slip_samples)
        print(f"\nslip_pips distribution ({n} samples):")
        print(f"  min={slip_samples[0]:.1f} p25={slip_samples[n//4]:.1f} med={slip_samples[n//2]:.1f}")
        print(f"  p75={slip_samples[3*n//4]:.1f} max={slip_samples[-1]:.1f}")
        print(f"  slip_cap={slip_cap}")


if __name__ == "__main__":
    main()
