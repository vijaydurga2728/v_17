import pytest
import pandas as pd
from pathlib import Path
import tempfile
from v17.data.parquet_store import write_bars_partitioned, read_bars
from v17.data.partition_guard import PartitionGuardError, assert_dev_only

HOLDOUT_START_NS = pd.Timestamp("2025-01-01 00:00:00", tz="UTC").value


def _bars(ts_list, symbol="EURUSD"):
    return pd.DataFrame({
        "ts_utc": ts_list,
        "symbol": symbol,
        "bid_c": [1.0] * len(ts_list),
        "ask_c": [1.00002] * len(ts_list),
        "spread_mid": [0.00002] * len(ts_list),
    })


def test_writer_tags_partition_correctly():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        dev_ns = pd.Timestamp("2024-06-01 00:00:00", tz="UTC").value
        hold_ns = pd.Timestamp("2025-06-01 00:00:00", tz="UTC").value
        df = _bars([dev_ns, hold_ns])
        write_bars_partitioned(df, root=d)
        assert (d / "bars" / "EURUSD" / "dev" / "year=2024" / "month=06").exists()
        assert (d / "bars" / "EURUSD" / "holdout" / "year=2025" / "month=06").exists()


def test_dev_only_read_rejects_holdout():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        hold_ns = pd.Timestamp("2025-06-01 00:00:00", tz="UTC").value
        df = _bars([hold_ns])
        write_bars_partitioned(df, root=d)
        with pytest.raises(PartitionGuardError):
            read_bars(root=d, symbol="EURUSD", partition="holdout", dev_only=True)


def test_assert_dev_only_blocks_holdout_flag():
    with pytest.raises(PartitionGuardError):
        assert_dev_only(partition="holdout")
    assert_dev_only(partition="dev")  # must not raise
