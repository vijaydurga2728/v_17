from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from v17.common.dtos import BacktestConfig, RunReport
from v17.common.types import RunId, Symbol
from v17.validation.evaluate import evaluate


def _report(**over: Any) -> RunReport:
    base: dict[str, Any] = {
        "run_id": RunId("x"),
        "config": BacktestConfig(
            symbol=Symbol("EURUSD"),
            start=datetime(2015, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        "trades": 500,
        "winrate": 0.55,
        "pf": 1.9,
        "sharpe": 2.1,
        "max_dd_pct": 5.0,
        "net_pnl": Decimal("12000"),
        "oos_trades": 250,
        "oos_pf": 1.85,
        "oos_sharpe": 2.0,
        "oos_max_dd_pct": 5.5,
        "walkforward_folds_passed": 6,
        "mc_p5_pf": 1.4,
        "mc_p95_max_dd_pct": 7.0,
    }
    base.update(over)
    return RunReport(**base)


def test_all_pass() -> None:
    ok, reasons = evaluate(_report())
    assert ok is True and reasons == []


def test_fail_pf() -> None:
    ok, reasons = evaluate(_report(pf=1.6, oos_pf=1.6))
    assert ok is False and any("pf" in r for r in reasons)


def test_fail_sharpe_and_winrate() -> None:
    ok, reasons = evaluate(_report(sharpe=1.0, oos_sharpe=1.0, winrate=0.40))
    assert ok is False and len(reasons) >= 2


def test_fail_max_dd() -> None:
    ok, reasons = evaluate(_report(max_dd_pct=7.0, oos_max_dd_pct=7.0))
    assert ok is False and any("dd" in r for r in reasons)


def test_fail_mc_fail_folds_fail_oos_count() -> None:
    ok, reasons = evaluate(
        _report(
            mc_p5_pf=1.1,
            mc_p95_max_dd_pct=9.0,
            walkforward_folds_passed=2,
            oos_trades=100,
        )
    )
    assert ok is False
    assert any("mc_p5_pf" in r for r in reasons)
    assert any("mc_p95" in r for r in reasons)
    assert any("folds" in r for r in reasons)
    assert any("oos_trades" in r for r in reasons)
