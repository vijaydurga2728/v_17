import json
from datetime import UTC, datetime
from pathlib import Path

from v17.common.types import Symbol
from v17.data.calendar.providers import FFCalendarProvider


def _seed(tmp_path: Path) -> None:
    recs = [
        {
            "title": "NFP",
            "country": "USD",
            "date": "2026-10-30T16:30:00+00:00",
            "impact": "High",
        },
        {
            "title": "UK GDP",
            "country": "GBP",
            "date": "2026-10-30T09:00:00+00:00",
            "impact": "Medium",
        },
    ]
    (tmp_path / "2026-W44.json").write_text(json.dumps(recs), encoding="utf-8")


def test_blackout_high_impact_only(tmp_path: Path) -> None:
    _seed(tmp_path)
    p = FFCalendarProvider(cache_dir=tmp_path)
    at = datetime(2026, 10, 30, 16, 32, tzinfo=UTC)
    assert p.is_blackout(Symbol("EURUSD"), at) is True
    assert p.is_blackout(Symbol("GBPUSD"), at) is True
    at2 = datetime(2026, 10, 30, 9, 1, tzinfo=UTC)
    assert p.is_blackout(Symbol("GBPUSD"), at2) is False


def test_blackout_window(tmp_path: Path) -> None:
    _seed(tmp_path)
    p = FFCalendarProvider(cache_dir=tmp_path)
    at = datetime(2026, 10, 30, 16, 36, tzinfo=UTC)
    assert p.is_blackout(Symbol("EURUSD"), at) is False


def test_events_range(tmp_path: Path) -> None:
    _seed(tmp_path)
    p = FFCalendarProvider(cache_dir=tmp_path)
    events = p.events(
        datetime(2026, 10, 30, tzinfo=UTC), datetime(2026, 10, 31, tzinfo=UTC)
    )
    assert len(events) == 2
