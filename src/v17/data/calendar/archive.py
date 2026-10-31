from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from dateutil import parser as dateparser

from v17.common.dtos import CalendarEvent

ALLOWED = {"USD", "EUR", "GBP"}
IMPACT: dict[str, str] = {"High": "high", "Medium": "medium", "Low": "low"}


def load_archive_dir(dir_: Path) -> list[CalendarEvent]:
    seen: set[tuple[object, ...]] = set()
    out: list[CalendarEvent] = []
    for p in sorted(dir_.glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        for item in raw:
            if item.get("country") not in ALLOWED:
                continue
            impact = IMPACT.get(item.get("impact", ""))
            if impact is None:
                continue
            at = dateparser.isoparse(item["date"]).astimezone(UTC)
            key = (at, item["country"], item.get("title", ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                CalendarEvent(
                    at=at,
                    currency=item["country"],
                    impact=impact,
                    title=item.get("title", ""),
                )
            )
    out.sort(key=lambda e: e.at)
    return out
