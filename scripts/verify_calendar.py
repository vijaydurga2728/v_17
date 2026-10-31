from __future__ import annotations

from pathlib import Path

from v17.data.calendar.archive import load_archive_dir

events = load_archive_dir(Path("data/calendar"))
print(f"loaded: {len(events)}")
print(f"first: {events[0]}")
print(f"last: {events[-1]}")
print(f"high only: {all(e.impact == 'high' for e in events)}")
by_cur = {"USD": 0, "EUR": 0, "GBP": 0}
for e in events:
    by_cur[e.currency] = by_cur.get(e.currency, 0) + 1
print(f"by currency: {by_cur}")
