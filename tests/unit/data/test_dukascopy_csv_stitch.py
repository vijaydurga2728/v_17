from pathlib import Path

import numpy as np

from v17.data.dukascopy_csv import stitch_pair

FIX = Path(__file__).parent.parent.parent / "fixtures" / "csv"


def test_stitch_mid_and_spread() -> None:
    df = stitch_pair([FIX / "EURUSD_tiny_bid.csv"], [FIX / "EURUSD_tiny_ask.csv"])
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume", "spread_pips"]
    assert len(df) == 3
    assert np.isclose(df["open"].iloc[0], 1.20987)
    assert np.isclose(df["spread_pips"].iloc[0], 0.8)


def test_stitch_monotonic_and_dedup(tmp_path: Path) -> None:
    (tmp_path / "dup.csv").write_text(
        '"Gmt time","Open","High","Low","Close","Volume"\n'
        "01.01.2015 00:00:00.000,1.1,1.2,1.0,1.15,1\n"
        "01.01.2015 00:00:00.000,1.1,1.2,1.0,1.15,1\n"
        "01.01.2015 00:02:00.000,1.1,1.2,1.0,1.15,1\n",
        encoding="utf-8",
    )
    (tmp_path / "dup_ask.csv").write_text(
        '"Gmt time","Open","High","Low","Close","Volume"\n'
        "01.01.2015 00:00:00.000,1.11,1.21,1.01,1.16,1\n"
        "01.01.2015 00:02:00.000,1.11,1.21,1.01,1.16,1\n",
        encoding="utf-8",
    )
    df = stitch_pair([tmp_path / "dup.csv"], [tmp_path / "dup_ask.csv"])
    assert len(df) == 2
    assert df["ts"].is_monotonic_increasing
