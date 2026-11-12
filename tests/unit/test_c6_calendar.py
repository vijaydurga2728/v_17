"""Cycle 6 calendar index + blackout + stale check."""
from pathlib import Path
import pandas as pd

from v17.data.c6_calendar import (
    build_calendar_index, load_calendar_index, is_blackout, is_calendar_stale,
)

FIX = Path(__file__).parent.parent / "fixtures"


def test_build_filters_high_impact_only(tmp_path):
    out = tmp_path / "ff_c6_index.parquet"
    n = build_calendar_index(FIX, out, ("USD", "AUD", "JPY"))
    assert n == 2  # NFP + AUD GDP
    df = load_calendar_index(out)
    assert set(df["impact"].unique()) == {"high"}
    assert set(df["currency"].unique()) == {"USD", "AUD"}


def test_is_blackout_window(tmp_path):
    out = tmp_path / "ff_c6_index.parquet"
    build_calendar_index(FIX, out, ("USD", "AUD", "JPY"))
    idx = load_calendar_index(out)
    nfp_ts = pd.Timestamp("2020-03-06 13:30:00", tz="UTC").value
    # Entry 10 min before NFP -> inside 15-min blackout.
    assert is_blackout(nfp_ts - 10 * 60 * 1_000_000_000, idx, 15) is True
    # 20 min before -> outside.
    assert is_blackout(nfp_ts - 20 * 60 * 1_000_000_000, idx, 15) is False


def test_is_calendar_stale(tmp_path):
    out = tmp_path / "ff_c6_index.parquet"
    build_calendar_index(FIX, out, ("USD", "AUD", "JPY"))
    idx = load_calendar_index(out)
    # max event is 2020-03-06 13:30 UTC. Sim ts 2020-03-10 00:00 UTC -> stale (>48h).
    stale_sim = pd.Timestamp("2020-03-10 00:00:00", tz="UTC").value
    assert is_calendar_stale(stale_sim, idx, max_age_hours=48) is True
    # Sim ts 2020-03-07 13:00 UTC -> 23.5h after -> fresh.
    fresh_sim = pd.Timestamp("2020-03-07 13:00:00", tz="UTC").value
    assert is_calendar_stale(fresh_sim, idx, max_age_hours=48) is False
