import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from v17.common.types import Symbol
from v17.data.calendar.providers import FFCalendarProvider
from v17.data.calendar.blackout import is_in_blackout, SYMBOL_CURRENCY_MAP


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


def test_blackout_window_minus10_plus20():
    event_ts = pd.Timestamp("2024-01-30 13:30:00", tz="UTC").value
    cal = pd.DataFrame({"timestamp_utc": [event_ts], "currency": ["USD"], "impact": ["High"]})
    # 15 min before — outside
    assert not is_in_blackout(event_ts - 15 * 60_000_000_000, cal, currencies=["USD"])
    # 5 min before — inside
    assert is_in_blackout(event_ts - 5 * 60_000_000_000, cal, currencies=["USD"])
    # at event — inside
    assert is_in_blackout(event_ts, cal, currencies=["USD"])
    # 15 min after — inside
    assert is_in_blackout(event_ts + 15 * 60_000_000_000, cal, currencies=["USD"])
    # 25 min after — outside
    assert not is_in_blackout(event_ts + 25 * 60_000_000_000, cal, currencies=["USD"])


def test_blackout_ignores_wrong_currency():
    event_ts = pd.Timestamp("2024-01-30 13:30:00", tz="UTC").value
    cal = pd.DataFrame({"timestamp_utc": [event_ts], "currency": ["EUR"], "impact": ["High"]})
    assert not is_in_blackout(event_ts, cal, currencies=["USD", "GBP"])


def test_empty_calendar_returns_false():
    cal = pd.DataFrame({"timestamp_utc": pd.Series([], dtype="int64"),
                        "currency": pd.Series([], dtype=object),
                        "impact": pd.Series([], dtype=object)})
    assert not is_in_blackout(1_700_000_000_000_000_000, cal, currencies=["USD", "EUR", "GBP"])


def test_symbol_map_includes_sb_symbols():
    assert set(SYMBOL_CURRENCY_MAP["EURUSD"]) == {"USD", "EUR"}
    assert set(SYMBOL_CURRENCY_MAP["GBPUSD"]) == {"USD", "GBP"}
    assert set(SYMBOL_CURRENCY_MAP["USATECHIDXUSD"]) == {"USD"}
