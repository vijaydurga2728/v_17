import json
from datetime import UTC
from pathlib import Path

from v17.data.calendar.archive import load_archive_dir


def test_load_merges_and_dedupes(tmp_path: Path) -> None:
    a = tmp_path / "2026-W40.json"
    b = tmp_path / "2026-W41.json"
    rec1 = {
        "title": "NFP",
        "country": "USD",
        "date": "2026-10-02T12:30:00-04:00",
        "impact": "High",
    }
    rec2 = {
        "title": "CPI",
        "country": "USD",
        "date": "2026-10-13T08:30:00-04:00",
        "impact": "High",
    }
    a.write_text(json.dumps([rec1, rec2]), encoding="utf-8")
    b.write_text(json.dumps([rec1]), encoding="utf-8")
    events = load_archive_dir(tmp_path)
    assert len(events) == 2
    assert all(e.at.tzinfo == UTC for e in events)
