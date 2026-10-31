from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from v17.common.dtos import BacktestConfig, RunReport
from v17.common.types import RunId, Symbol
from v17.validation.gate import GateWriter


def _report() -> RunReport:
    cfg = BacktestConfig(
        symbol=Symbol("EURUSD"),
        start=datetime(2015, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return RunReport(
        run_id=RunId("abc"),
        config=cfg,
        trades=250,
        winrate=0.55,
        pf=1.9,
        sharpe=2.1,
        max_dd_pct=5.0,
        net_pnl=Decimal("12000"),
        oos_trades=250,
        oos_pf=1.85,
        oos_sharpe=2.0,
        oos_max_dd_pct=5.5,
        walkforward_folds_passed=6,
        mc_p5_pf=1.4,
        mc_p95_max_dd_pct=7.0,
    )


def test_write_then_active(tmp_path: Path) -> None:
    g = GateWriter(tmp_path)
    assert g.is_active() is False
    g.write_sentinel(_report(), now=datetime(2026, 10, 28, tzinfo=UTC))
    assert g.is_active() is True
    active = g.read_active()
    assert active is not None
    assert active["run_id"] == "abc"


def test_revoke(tmp_path: Path) -> None:
    g = GateWriter(tmp_path)
    g.write_sentinel(_report())
    assert g.revoke() is True
    assert g.is_active() is False
    assert g.revoke() is False


def test_read_active_none_when_absent(tmp_path: Path) -> None:
    g = GateWriter(tmp_path)
    assert g.read_active() is None
