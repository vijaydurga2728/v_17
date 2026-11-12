# tests/integration/test_c6_cli_grid.py
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from typer.testing import CliRunner

from v17.cli_c6 import app as c6_app
from tests.integration.test_c6_runner import _synthetic_m5


def _write_m5(df, root, sym, year):
    out = root / sym / f"year={year}" / "part-00.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out, compression="zstd")


def test_grid_cli_writes_48_rows(tmp_path):
    spx_root = tmp_path / "spx"; fx_root = tmp_path / "fx"
    spx = _synthetic_m5(10, 0.05, "USA500IDXUSD")
    aud = _synthetic_m5(10, 0.05, "AUDUSD")
    jpy = _synthetic_m5(10, 0.05, "USDJPY")
    _write_m5(spx, spx_root, "USA500IDXUSD", 2020)
    _write_m5(aud, fx_root, "AUDUSD", 2020)
    _write_m5(jpy, fx_root, "USDJPY", 2020)
    cal = tmp_path / "cal.parquet"
    pd.DataFrame({"ts_utc": [], "currency": [], "impact": [], "title": []}).to_parquet(cal)
    out_csv = tmp_path / "grid.csv"
    r = CliRunner().invoke(c6_app, ["grid",
        "--spx-root", str(spx_root), "--fx-root", str(fx_root), "--calendar", str(cal),
        "--dev-start", "2020-01-01", "--dev-end", "2020-01-15",
        "--out-csv", str(out_csv)])
    assert r.exit_code == 0, r.output
    assert out_csv.exists()
    assert len(pd.read_csv(out_csv)) == 48
