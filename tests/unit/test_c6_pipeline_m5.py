from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from v17.data.c6_pipeline import build_m5_paired


def _write_m1_paired_fixture(root: Path, symbol: str, year: int):
    # Build 20 synthetic M1 bars across 4 M5 buckets, varying tick counts.
    ts0 = pd.Timestamp(f"{year}-01-01 08:00:00", tz="UTC").value  # ns
    rows = []
    for i in range(20):
        rows.append({
            "ts_utc": ts0 + i * 60_000_000_000,
            "symbol": symbol,
            "bid_o": 1.0, "bid_h": 1.0, "bid_l": 1.0, "bid_c": 1.0,
            "ask_o": 1.0, "ask_h": 1.0, "ask_l": 1.0, "ask_c": 1.0,
            "bid_volume": 1, "ask_volume": 1, "spread_mid": 0.0,
        })
    # Drop bars 5-9 to leave bucket 08:05-08:10 with 0 ticks (missing bucket)
    # and shrink bucket 08:10-08:15 to 2 ticks (ticks 10,11 only). We keep
    # ticks 0-4 (bucket 1: 5), remove 5-9, keep 10-11 (bucket 3: 2),
    # remove 12-14, keep 15-19 (bucket 4: 5).
    keep_indices = {0, 1, 2, 3, 4, 10, 11, 15, 16, 17, 18, 19}
    rows = [r for i, r in enumerate(rows) if i in keep_indices]
    df = pd.DataFrame(rows)
    out = root / symbol / f"year={year}" / "part-00.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out, compression="zstd")


def test_build_m5_drops_low_tick_bars(tmp_path):
    m1 = tmp_path / "m1"
    m5 = tmp_path / "m5"
    _write_m1_paired_fixture(m1, "AUDUSD", 2020)
    n = build_m5_paired(m1, m5, "AUDUSD", 2020)
    # Expect 2 kept buckets (the ones with 5 ticks each). The 2-tick bucket is dropped.
    assert n == 2
    out = m5 / "AUDUSD" / "year=2020" / "part-00.parquet"
    df = pq.read_table(out).to_pandas()
    assert (df["n_m1_ticks"] >= 5).all()
    assert len(df) == 2
