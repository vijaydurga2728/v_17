# tests/unit/test_c6_pipeline_m1.py
from pathlib import Path

import pyarrow.parquet as pq

from v17.data.c6_pipeline import ingest_m1_paired

FIX = Path(__file__).parent.parent / "fixtures"


def test_ingest_writes_parquet_with_expected_schema(tmp_path):
    n = ingest_m1_paired(
        FIX / "c6_sample_bid.csv",
        FIX / "c6_sample_ask.csv",
        "AUDUSD",
        tmp_path,
    )
    assert n == 3
    out = tmp_path / "AUDUSD" / "year=2020" / "part-00.parquet"
    assert out.exists()
    df = pq.read_table(out).to_pandas()
    assert set(df.columns) >= {
        "ts_utc", "symbol", "bid_o", "bid_h", "bid_l", "bid_c",
        "ask_o", "ask_h", "ask_l", "ask_c", "bid_volume", "ask_volume", "spread_mid",
    }
    assert (df["symbol"] == "AUDUSD").all()
    assert len(df) == 3


def test_ingest_spread_mid_computation(tmp_path):
    ingest_m1_paired(
        FIX / "c6_sample_bid.csv",
        FIX / "c6_sample_ask.csv",
        "AUDUSD",
        tmp_path,
    )
    out = tmp_path / "AUDUSD" / "year=2020" / "part-00.parquet"
    df = pq.read_table(out).to_pandas().sort_values("ts_utc").reset_index(drop=True)
    # First row: bid_c=0.70015, ask_c=0.70018 -> spread = 0.00003 = 0.3 pips
    assert abs(df.loc[0, "spread_mid"] - 0.00003) < 1e-9
