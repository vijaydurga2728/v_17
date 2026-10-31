from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from v17.backtest.report import run_id_from_cfg, write_run
from v17.common.dtos import BacktestConfig, Trade
from v17.common.types import Side, SignalId, Symbol, Ticket


def _cfg() -> BacktestConfig:
    return BacktestConfig(
        symbol=Symbol("EURUSD"),
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 3, 31, tzinfo=UTC),
    )


def test_run_id_deterministic() -> None:
    a = run_id_from_cfg(_cfg())
    b = run_id_from_cfg(_cfg())
    assert a == b and len(a) == 16


def test_write_run_creates_files(tmp_path: Path) -> None:
    trade = Trade(
        ticket=Ticket(1),
        signal_id=SignalId("abc"),
        symbol=Symbol("EURUSD"),
        side=Side.BUY,
        size_lots=Decimal("0.1"),
        entry=Decimal("1.1000"),
        sl=Decimal("1.0990"),
        tp=Decimal("1.1015"),
        opened_at=datetime(2024, 1, 2, 8, 0, tzinfo=UTC),
        closed_at=datetime(2024, 1, 2, 9, 0, tzinfo=UTC),
        close_price=Decimal("1.1015"),
        pnl=Decimal("15"),
        reason="tp",
    )
    equity = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")],
            "equity": [100015.0, 100015.0],
        }
    )
    metrics = {"pf": 1.8, "sharpe": 2.0, "trades": 1}
    wf = {"folds_passed": 6}
    mc = {"p5_pf": 1.4}
    write_run(tmp_path, [trade], equity, metrics, wf, mc)
    assert (tmp_path / "trades.parquet").exists()
    assert (tmp_path / "equity.parquet").exists()
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "walkforward.json").exists()
    assert (tmp_path / "montecarlo.json").exists()
