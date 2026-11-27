"""Regression tests for scripts/live_ftmo_runner.py calendar sync and spread gate."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import live_ftmo_runner as R  # noqa: E402


def test_spread_at_limit_is_allowed_despite_float_error() -> None:
    # Real EURUSD case from execution_audit.jsonl 2026-11-23: 1.0 pip rejected.
    spread = 0.00010000000000021103  # exact logged value of ask - bid
    assert spread > 0.0001  # the float artefact that caused the bug
    assert not R.spread_exceeds_limit(spread, 0.0001, 0.00001)


def test_spread_above_limit_is_rejected() -> None:
    assert R.spread_exceeds_limit(0.00011, 0.0001, 0.00001)


class _Resp:
    def __init__(self, payload: list[dict]) -> None:
        self._b = json.dumps(payload).encode()

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def read(self) -> bytes:
        return self._b


FEED = [
    {"title": "Core PCE", "country": "USD", "date": "2026-11-25T08:30:00-05:00", "impact": "High"},
    {"title": "AUD CPI", "country": "AUD", "date": "2026-11-24T19:30:00-05:00", "impact": "High"},
    {"title": "Speech", "country": "USD", "date": "2026-11-25T10:00:00-05:00", "impact": "Low"},
]


def test_stale_cache_is_refetched(tmp_path: Path) -> None:
    cache = tmp_path / "cal.json"
    cache.write_text(json.dumps({"timestamp": time.time() - 5 * 86400, "events": [{"x": 1}]}))
    cal = R.LiveEconomicCalendar(cache)
    with mock.patch("urllib.request.urlopen", return_value=_Resp(FEED)) as m:
        cal.sync()
    assert m.call_count == 1
    assert [e["title"] for e in cal.events] == ["Core PCE"]


def test_empty_week_does_not_refetch_every_poll(tmp_path: Path) -> None:
    cal = R.LiveEconomicCalendar(tmp_path / "cal.json")
    with mock.patch("urllib.request.urlopen", return_value=_Resp([])) as m:
        cal.sync()
        cal.sync()
        cal.sync()
    assert m.call_count == 1
    assert cal.events == []


def test_failed_fetch_backs_off(tmp_path: Path) -> None:
    cal = R.LiveEconomicCalendar(tmp_path / "cal.json")
    with mock.patch("urllib.request.urlopen", side_effect=OSError("down")) as m:
        cal.sync()
        cal.sync()
    assert m.call_count == 1
