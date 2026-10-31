from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dateutil import parser as dateparser

from v17.common.dtos import CalendarEvent

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
ALLOWED = {"USD", "EUR", "GBP"}
IMPACT: dict[str, str] = {"High": "high", "Medium": "medium", "Low": "low"}


def fetch_current_week(
    http: httpx.Client, cache_dir: Path, now: datetime
) -> list[CalendarEvent]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    iso_year, iso_week, _ = now.astimezone(UTC).isocalendar()
    cache = cache_dir / f"{iso_year}-W{iso_week:02d}.json"
    resp = http.get(FF_URL, timeout=15.0)
    resp.raise_for_status()
    cache.write_bytes(resp.content)
    raw = json.loads(resp.content)
    out: list[CalendarEvent] = []
    for item in raw:
        if item.get("country") not in ALLOWED:
            continue
        impact_raw = item.get("impact", "")
        impact = IMPACT.get(impact_raw)
        if impact is None:
            continue
        at = dateparser.isoparse(item["date"]).astimezone(UTC)
        out.append(
            CalendarEvent(
                at=at,
                currency=item["country"],
                impact=impact,
                title=item.get("title", ""),
            )
        )
    return out
