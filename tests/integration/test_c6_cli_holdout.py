"""Integration tests for holdout CLI commands (backtest, mcpt-holdout, holdout-report)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from v17.cli_c6 import app as c6_app


def test_holdout_report_md(tmp_path: Path) -> None:
    tl = tmp_path / "ho_tl.csv"
    pd.DataFrame(
        {
            "net_pnl_usd": [40, 50, -20, 60] * 100,
            "entry_ts_ns": [i * 86_400_000_000_000 for i in range(400)],
            "equity_sod": [10000] * 400,
        }
    ).to_csv(tl, index=False)
    mcpt = tmp_path / "mcpt.json"
    mcpt.write_text(json.dumps({"p_sharpe": 0.07}))
    out = tmp_path / "ho.md"
    r = CliRunner().invoke(
        c6_app,
        [
            "holdout-report",
            "--dev-sharpe", "1.2",
            "--trade-log", str(tl),
            "--mcpt-json", str(mcpt),
            "--out-md", str(out),
        ],
    )
    assert r.exit_code == 0, r.output
    txt = out.read_text()
    assert "H1" in txt and "H5" in txt
