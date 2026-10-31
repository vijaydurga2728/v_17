"""Audit backtest vs live asymmetries:
(a) is_locked_today reset — code path check
(b) Sunday open — bars present at Sunday 22:00-23:59 UTC?
(c) Daily rollover 22:00 UTC — does it overlap SB/Judas killzones?
"""
from __future__ import annotations

from datetime import UTC, datetime

from v17.common.types import TF, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.setups.sessions import in_judas_window, in_silver_bullet_window


def check_sunday_bars() -> None:
    s = get_settings()
    s.ensure_dirs()
    p = ParquetBarProvider(s.parquet_root)
    bars = list(
        p.bars(
            Symbol("EURUSD"),
            TF.M1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 31, tzinfo=UTC),
        )
    )
    sunday_bars = [b for b in bars if b.ts.weekday() == 6]
    friday_night = [b for b in bars if b.ts.weekday() == 4 and b.ts.hour >= 22]
    saturday_bars = [b for b in bars if b.ts.weekday() == 5]
    print(f"Jan 2024 EURUSD bars: {len(bars):,}")
    print(f"  Sunday bars (weekday=6): {len(sunday_bars)}")
    print(f"  Saturday bars (weekday=5): {len(saturday_bars)}")
    print(f"  Friday 22:00+ UTC: {len(friday_night)}")


def check_rollover_overlap() -> None:
    # SB window: 03:00-04:00 NY. EST=UTC-5 (winter) → 08:00-09:00 UTC. EDT=UTC-4 (summer) → 07:00-08:00 UTC.
    # Judas: 07:00-08:30 London. GMT=UTC (winter) → 07:00-08:30 UTC. BST=UTC+1 (summer) → 06:00-07:30 UTC.
    # Rollover: 22:00 UTC daily (broker-dependent, usually 21:00-23:00 UTC spike window).
    rollover_start_utc = 22
    rollover_end_utc = 23
    print(f"Rollover window: {rollover_start_utc:02d}:00-{rollover_end_utc:02d}:00 UTC")
    print(
        "SB window: 07-09 UTC (winter/summer). Judas window: 06-08:30 UTC."
    )
    print("Overlap with 22-23 UTC rollover: NONE.")


def check_lockout_reset() -> None:
    # Verify loop.py day-change block resets is_locked_today, daily_realized_pnl, trades_today.
    from pathlib import Path
    loop_py = Path("src/v17/backtest/loop.py").read_text()
    checks = {
        "is_locked_today reset": '"is_locked_today": False' in loop_py,
        "daily_realized_pnl reset": 'daily_realized_pnl": Decimal("0")' in loop_py,
        "trades_today reset": '"trades_today": 0' in loop_py,
        "fired_today reset": "fired_today = set()" in loop_py,
    }
    for k, v in checks.items():
        print(f"  {k}: {'OK' if v else 'MISSING'}")


def check_sunday_killzone_overlap() -> None:
    # Does any Sunday bar fall inside SB or Judas window?
    s = get_settings()
    s.ensure_dirs()
    p = ParquetBarProvider(s.parquet_root)
    bars = list(
        p.bars(
            Symbol("EURUSD"),
            TF.M1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 12, 31, tzinfo=UTC),
        )
    )
    sunday_in_sb = sum(1 for b in bars if b.ts.weekday() == 6 and in_silver_bullet_window(b.ts))
    sunday_in_judas = sum(1 for b in bars if b.ts.weekday() == 6 and in_judas_window(b.ts))
    print(f"2024 Sunday bars inside SB window: {sunday_in_sb}")
    print(f"2024 Sunday bars inside Judas window: {sunday_in_judas}")


if __name__ == "__main__":
    print("=== (a) Lockout reset code paths ===")
    check_lockout_reset()
    print("\n=== (b) Sunday / Saturday / Friday-late bars ===")
    check_sunday_bars()
    print("\n=== (b2) Sunday overlap with killzones ===")
    check_sunday_killzone_overlap()
    print("\n=== (c) Rollover vs killzone overlap ===")
    check_rollover_overlap()
