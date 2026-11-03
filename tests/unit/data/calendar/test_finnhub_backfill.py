from unittest.mock import patch
from v17.data.calendar.finnhub_client import backfill_calendar


MOCK_RESPONSE = {
    "economicCalendar": [
        {"time": "2024-01-30 13:30:00", "country": "US", "impact": "high",
         "event": "Core PCE Price Index m/m"},
        {"time": "2024-01-31 10:00:00", "country": "EU", "impact": "medium",
         "event": "German Prelim CPI"},
    ]
}


def test_backfill_filters_high_impact_only():
    with patch("v17.data.calendar.finnhub_client._call_api", return_value=MOCK_RESPONSE):
        df = backfill_calendar(
            start="2024-01-30", end="2024-01-31",
            currencies=["USD", "EUR", "GBP"], impact="high",
        )
    assert len(df) == 1
    assert df.iloc[0]["event"] == "Core PCE Price Index m/m"
    assert df.iloc[0]["currency"] == "USD"


def test_backfill_produces_utc_ns_timestamps():
    import pandas as pd
    with patch("v17.data.calendar.finnhub_client._call_api", return_value=MOCK_RESPONSE):
        df = backfill_calendar(
            start="2024-01-30", end="2024-01-31",
            currencies=["USD"], impact="high",
        )
    expected = pd.Timestamp("2024-01-30 13:30:00", tz="UTC").value
    assert df.iloc[0]["timestamp_utc"] == expected


def test_backfill_filters_currency_whitelist():
    with patch("v17.data.calendar.finnhub_client._call_api", return_value=MOCK_RESPONSE):
        df = backfill_calendar(
            start="2024-01-30", end="2024-01-31",
            currencies=["EUR"], impact="high",
        )
    # Only USD event is high-impact; filtered out by currency
    assert len(df) == 0
