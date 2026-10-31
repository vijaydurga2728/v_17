from datetime import UTC, datetime
from pathlib import Path

import httpx

from v17.data.calendar.ff_json import fetch_current_week

FIX = (
    Path(__file__).parent.parent.parent.parent
    / "fixtures"
    / "calendar"
    / "ff_sample.json"
)


def test_fetch_filters_and_parses(tmp_path: Path) -> None:
    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FIX.read_bytes())

    transport = httpx.MockTransport(_handler)
    client = httpx.Client(transport=transport)
    now = datetime(2026, 10, 28, tzinfo=UTC)
    events = fetch_current_week(client, tmp_path, now)
    assert len(events) == 3
    assert all(e.currency in {"USD", "EUR", "GBP"} for e in events)
    nfp = next(e for e in events if "Non-Farm" in e.title)
    assert nfp.at == datetime(2026, 10, 30, 16, 30, tzinfo=UTC)
    assert any(p.suffix == ".json" for p in tmp_path.iterdir())
