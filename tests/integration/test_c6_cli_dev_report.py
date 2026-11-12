# tests/integration/test_c6_cli_dev_report.py
from pathlib import Path
import json
from typer.testing import CliRunner

from v17.cli_c6 import app as c6_app


def test_dev_report_generates_markdown(tmp_path):
    runner = CliRunner()
    # Minimal fake inputs.
    grid = tmp_path / "grid.csv"
    import pandas as pd
    pd.DataFrame([{"K": 0.3, "slope_window": 12, "C": 0.4,
                     "sharpe": 1.2, "pf": 1.4, "trade_count": 900,
                     "max_daily_loss_pct": -0.02, "max_consec_losing_days": 3}]).to_csv(grid, index=False)
    tl = tmp_path / "tl.csv"
    pd.DataFrame({"net_pnl_usd": [50, 60, -30, 70, -25] * 200,
                   "entry_ts_ns": [i * 1_000_000_000_000 for i in range(1000)],
                   "equity_sod": [10000] * 1000}).to_csv(tl, index=False)
    mcpt = tmp_path / "mcpt.json"; mcpt.write_text(json.dumps({"p_sharpe": 0.02, "observed_sharpe": 1.2}))
    paired = tmp_path / "paired.json"; paired.write_text(json.dumps({"A1": 0.02, "A2": 0.05, "A3": 0.07}))
    out = tmp_path / "report.md"
    r = runner.invoke(c6_app, ["dev-report", "--grid-csv", str(grid), "--trade-log", str(tl),
                                  "--mcpt-json", str(mcpt), "--paired-json", str(paired),
                                  "--out-md", str(out)])
    assert r.exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert "D1" in text and "A1" in text
    assert "best_config" in text or "Best config" in text
