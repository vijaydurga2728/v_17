from decimal import Decimal

import pandas as pd

from v17.backtest.metrics import (
    daily_returns_from_equity,
    max_drawdown_pct,
    profit_factor,
    sharpe,
    winrate,
)


def test_pf() -> None:
    assert profit_factor([Decimal("200"), Decimal("-100")]) == 2.0


def test_pf_empty() -> None:
    assert profit_factor([]) == 0.0


def test_winrate() -> None:
    assert winrate([Decimal("1"), Decimal("-1"), Decimal("1")]) == 2 / 3


def test_max_dd_pct() -> None:
    eq = [Decimal("100"), Decimal("120"), Decimal("90"), Decimal("110")]
    assert abs(max_drawdown_pct(eq) - 25.0) < 1e-9


def test_sharpe_zero_variance() -> None:
    assert sharpe([0.01, 0.01, 0.01]) == 0.0


def test_sharpe_nonzero() -> None:
    s = sharpe([0.01, -0.005, 0.015, 0.0, 0.02])
    assert s > 0


def test_daily_returns_from_equity() -> None:
    curve = pd.DataFrame({"equity": [100.0, 110.0, 99.0]})
    r = daily_returns_from_equity(curve)
    assert abs(r[0] - 0.1) < 1e-9
    assert abs(r[1] - (-0.1)) < 1e-9
