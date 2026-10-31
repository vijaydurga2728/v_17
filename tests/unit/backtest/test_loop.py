from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from v17.backtest.loop import EventLoop
from v17.backtest.precompute import precompute
from v17.common.types import Symbol
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet


def _bars_slice() -> pd.DataFrame:
    # 3 days of 1m bars, slow drift. Short enough to run fast.
    n = 60 * 24 * 3
    ts = pd.date_range("2024-06-03", periods=n, freq="1min", tz="UTC")
    base = 1.08 + np.linspace(0, 0.005, n) + np.sin(np.arange(n) / 60) * 0.0005
    return pd.DataFrame(
        {
            "ts": ts,
            "open": base,
            "high": base + 0.0003,
            "low": base - 0.0003,
            "close": base,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.3),
        }
    )


def test_loop_runs_without_crash() -> None:
    pre = precompute(_bars_slice(), Symbol("EURUSD"))
    loop = EventLoop(Symbol("EURUSD"), [SilverBullet()], DefaultRiskEngine(), pre)
    start = datetime(2024, 6, 3, tzinfo=UTC)
    end = datetime(2024, 6, 5, 23, 59, tzinfo=UTC)
    trades, eq = loop.run(start, end, Decimal("100000"))
    assert isinstance(trades, list)
    assert isinstance(eq, pd.DataFrame)
    assert "equity" in eq.columns
