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


def test_loop_force_closes_at_end_of_data() -> None:
    # Verify that an open trade at the end of simulation is closed with reason="end_of_data"
    from v17.common.dtos import Signal
    from v17.common.types import Side, SignalId
    pre = precompute(_bars_slice(), Symbol("EURUSD"))

    class AlwaysFiresSetup:
        name = "silver_bullet"
        def evaluate(self, snap: object, now: datetime, bars: object) -> Signal | None:
            # Fire a signal near the end
            if now == datetime(2024, 6, 5, 23, 50, tzinfo=UTC):
                return Signal(
                    id=SignalId("end_test_sig"),
                    symbol=Symbol("EURUSD"),
                    setup="silver_bullet",
                    side=Side.BUY,
                    at=now,
                    entry=Decimal("1.0850"),
                    sl=Decimal("1.0800"),  # wide SL so it doesn't trigger on remaining bars
                    tp=Decimal("1.0950"),  # wide TP so it doesn't trigger
                    rr=Decimal("2.0"),
                    confluence={"bias": True, "fvg": True, "ob": True, "mss": True, "sweep": True},
                )
            return None

    loop = EventLoop(Symbol("EURUSD"), [AlwaysFiresSetup()], DefaultRiskEngine(), pre)  # type: ignore[list-item]
    start = datetime(2024, 6, 3, tzinfo=UTC)
    end = datetime(2024, 6, 5, 23, 59, tzinfo=UTC)
    trades, eq = loop.run(start, end, Decimal("100000"))
    if trades:
        last_trade = trades[-1]
        assert last_trade.reason == "end_of_data"
        assert last_trade.closed_at is not None
        assert last_trade.close_price is not None
