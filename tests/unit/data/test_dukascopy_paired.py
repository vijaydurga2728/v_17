import pandas as pd
from pathlib import Path
import tempfile
from v17.data.dukascopy_csv import load_paired_bars


def _write_sample_csv(path: Path, header: str, rows: list[str]) -> None:
    path.write_text(header + "\n" + "\n".join(rows) + "\n")


def test_paired_load_joins_on_time_and_computes_spread():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bid = d / "EURUSD_bid.csv"
        ask = d / "EURUSD_ask.csv"
        header = "Time (EET),Open,High,Low,Close,Volume"
        _write_sample_csv(bid, header, [
            "2015.01.02 00:00:00,1.21000,1.21005,1.20995,1.21002,10",
            "2015.01.02 00:01:00,1.21002,1.21010,1.21001,1.21008,12",
        ])
        _write_sample_csv(ask, header, [
            "2015.01.02 00:00:00,1.21002,1.21007,1.20997,1.21004,10",
            "2015.01.02 00:01:00,1.21004,1.21012,1.21003,1.21010,12",
        ])
        df = load_paired_bars(bid, ask, symbol="EURUSD")
        expected_cols = [
            "ts_utc", "symbol",
            "bid_o", "bid_h", "bid_l", "bid_c",
            "ask_o", "ask_h", "ask_l", "ask_c",
            "bid_volume", "ask_volume", "spread_mid",
        ]
        for c in expected_cols:
            assert c in df.columns, f"missing column: {c}"
        assert len(df) == 2
        assert df.iloc[0]["symbol"] == "EURUSD"
        assert df.iloc[0]["bid_c"] == 1.21002
        assert df.iloc[0]["ask_c"] == 1.21004
        assert abs(df.iloc[0]["spread_mid"] - 0.00002) < 1e-9


def test_eet_timezone_converts_to_utc():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bid = d / "b.csv"
        ask = d / "a.csv"
        header = "Time (EET),Open,High,Low,Close,Volume"
        _write_sample_csv(bid, header, ["2015.01.02 02:00:00,1,1,1,1,1"])
        _write_sample_csv(ask, header, ["2015.01.02 02:00:00,1,1,1,1,1"])
        df = load_paired_bars(bid, ask, symbol="X")
        expected_utc_ns = pd.Timestamp("2015-01-02 00:00:00", tz="UTC").value
        assert df.iloc[0]["ts_utc"] == expected_utc_ns


def test_inner_join_drops_rows_present_in_only_one_side():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bid = d / "b.csv"
        ask = d / "a.csv"
        header = "Time (EET),Open,High,Low,Close,Volume"
        _write_sample_csv(bid, header, [
            "2015.01.02 00:00:00,1,1,1,1.0,1",
            "2015.01.02 00:01:00,1,1,1,1.0,1",
        ])
        _write_sample_csv(ask, header, [
            "2015.01.02 00:00:00,1,1,1,1.00002,1",
        ])
        df = load_paired_bars(bid, ask, symbol="X")
        assert len(df) == 1  # only the matching minute survives
