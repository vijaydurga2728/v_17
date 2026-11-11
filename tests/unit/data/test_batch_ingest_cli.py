import pandas as pd
from pathlib import Path
from v17.data.cli import ingest_from_manifest


def _write(p: Path, rows: list[str]) -> None:
    header = "Time (EET),Open,High,Low,Close,Volume"
    p.write_text(header + "\n" + "\n".join(rows) + "\n")


def test_ingest_from_manifest_writes_partitioned_parquet(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "EURUSD_bid.csv", ["2015.01.02 02:00:00,1,1,1,1.00000,1"])
    _write(src / "EURUSD_ask.csv", ["2015.01.02 02:00:00,1,1,1,1.00002,1"])

    manifest = {
        "root": str(src),
        "symbols": [{
            "symbol": "EURUSD",
            "pairs": [{"bid": "EURUSD_bid.csv", "ask": "EURUSD_ask.csv"}],
        }],
    }
    out = tmp_path / "out"
    ingest_from_manifest(manifest, out_root=out)
    files = list((out / "bars" / "EURUSD" / "dev").rglob("*.parquet"))
    assert len(files) >= 1
