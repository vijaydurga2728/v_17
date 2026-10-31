"""How many high-impact events fall inside SB/Judas killzone windows?"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from v17.common.types import Symbol
from v17.data.calendar.archive import load_archive_dir
from v17.data.calendar.blackout import AFFECTED
from v17.setups.sessions import in_judas_window, in_silver_bullet_window

events = load_archive_dir(Path("data/calendar"))
start = datetime(2021, 1, 1, tzinfo=UTC)
end = datetime(2025, 1, 1, tzinfo=UTC)
events = [e for e in events if start <= e.at < end and e.impact == "high"]
print(f"high-impact 2021-2024: {len(events)}")

for sym in (Symbol("EURUSD"), Symbol("GBPUSD")):
    affected = AFFECTED[sym]
    sym_events = [e for e in events if e.currency in affected]
    sb_overlap = sum(1 for e in sym_events if in_silver_bullet_window(e.at))
    judas_overlap = sum(1 for e in sym_events if in_judas_window(e.at))
    print(f"\n{sym}: affected={affected}, events={len(sym_events)}")
    print(f"  in SB window:    {sb_overlap}")
    print(f"  in Judas window: {judas_overlap}")
    if sb_overlap + judas_overlap > 0:
        samples = [e for e in sym_events if in_silver_bullet_window(e.at) or in_judas_window(e.at)][:5]
        print("  samples:")
        for e in samples:
            print(f"    {e.at.isoformat()} {e.currency} {e.title[:60]}")
