from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "demo_poll_watchdog",
    Path(__file__).resolve().parents[3] / "scripts" / "demo_poll_watchdog.py",
)
assert _spec is not None and _spec.loader is not None
wd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wd)


def test_age_fresh_and_stale(tmp_path: Path) -> None:
    now = datetime(2026, 11, 17, 18, 0, tzinfo=UTC)
    f = tmp_path / "last_poll.txt"
    f.write_text((now - timedelta(hours=1)).isoformat(), encoding="utf-8")
    assert wd.poll_age_hours(f, now) == 1.0
    f.write_text((now - timedelta(days=5)).isoformat(), encoding="utf-8")
    assert wd.poll_age_hours(f, now) > wd.MAX_AGE_H


def test_missing_file_is_none(tmp_path: Path) -> None:
    assert wd.poll_age_hours(tmp_path / "nope.txt", datetime.now(UTC)) is None
