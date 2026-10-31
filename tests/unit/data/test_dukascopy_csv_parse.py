from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from v17.data.dukascopy_csv import read_file

FIX = Path(__file__).parent.parent.parent / "fixtures" / "csv" / "EURUSD_tiny_bid.csv"


def test_read_file_bid_shape() -> None:
    df = read_file(FIX, side="bid")
    assert list(df.columns) == ["ts", "open_bid", "high_bid", "low_bid", "close_bid", "volume"]
    assert len(df) == 3
    assert "UTC" in str(df["ts"].dtype) and "datetime64" in str(df["ts"].dtype)
    assert df["ts"].iloc[0] == pd.Timestamp(datetime(2015, 1, 1, tzinfo=UTC))
    assert df["open_bid"].iloc[0] == 1.20983


def test_read_file_ask_prefix(tmp_path: Path) -> None:
    tgt = tmp_path / "ask.csv"
    tgt.write_text(FIX.read_text(encoding="utf-8"), encoding="utf-8")
    df = read_file(tgt, side="ask")
    assert "open_ask" in df.columns and "high_ask" in df.columns
