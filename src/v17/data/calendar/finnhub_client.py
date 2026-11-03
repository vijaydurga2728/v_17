import os

_COUNTRY_TO_CCY = {
    "US": "USD",
    "EU": "EUR",
    "DE": "EUR",
    "FR": "EUR",
    "GB": "GBP",
    "UK": "GBP",
}


def _call_api(client, start: str, end: str) -> dict:
    return client.calendar_economic(_from=start, to=end)


def backfill_calendar(start: str, end: str, currencies: list[str], impact: str = "high"):
    import pandas as pd
    api_key = os.environ.get("FINNHUB_API_KEY")
    client = None
    if api_key:
        try:
            import finnhub
            client = finnhub.Client(api_key=api_key)
        except ImportError:
            client = None
    raw = _call_api(client, start, end)
    rows: list[dict] = []
    for ev in raw.get("economicCalendar", []) or []:
        ccy = _COUNTRY_TO_CCY.get(ev.get("country"), None)
        if ccy not in currencies:
            continue
        if ev.get("impact", "").lower() != impact.lower():
            continue
        ts = pd.Timestamp(ev["time"], tz="UTC")
        rows.append({
            "timestamp_utc": ts.value,
            "currency": ccy,
            "impact": ev["impact"].capitalize(),
            "event": ev["event"],
        })
    return pd.DataFrame(rows, columns=["timestamp_utc", "currency", "impact", "event"])
