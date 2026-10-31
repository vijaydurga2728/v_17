from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from v17.common.dtos import StructureSnapshot, Sweep, Swing, Zone
from v17.common.types import TF, Bias, Side, Symbol
from v17.setups.silver_bullet import SilverBullet


def _bars_sb() -> pd.DataFrame:
    ts = pd.date_range("2024-06-05 07:00", periods=60, freq="1min", tz="UTC")
    base = 1.08500
    opens = [base] * 60
    closes = [base + 0.00005] * 60
    closes[55] = base + 0.0005
    highs = [c + 0.00005 for c in closes]
    lows = [o - 0.00005 for o in opens]
    return pd.DataFrame(
        {
            "ts": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1] * 60,
            "spread_pips": [0.3] * 60,
        }
    )


def test_sb_emits_bull_signal() -> None:
    now = datetime(2024, 6, 5, 7, 55, tzinfo=UTC)
    bars = _bars_sb()
    zone = Zone(
        kind="fvg",
        side=Side.BUY,
        tf=TF.M15,
        created_at=datetime(2024, 6, 5, 6, 45, tzinfo=UTC),
        top=Decimal("1.0860"),
        bottom=Decimal("1.0845"),
    )
    sweep = Sweep(
        kind="ssl",
        tf=TF.M15,
        at=datetime(2024, 6, 5, 6, 30, tzinfo=UTC),
        level=Decimal("1.0840"),
    )
    mss = Swing(
        kind="mss",
        side=Side.BUY,
        tf=TF.M1,
        at=datetime(2024, 6, 5, 7, 55, tzinfo=UTC),
        price=Decimal("1.0855"),
    )
    snap = StructureSnapshot(
        symbol=Symbol("EURUSD"),
        at=now,
        bias=Bias.BULL,
        zones=[zone],
        swings=[mss],
        sweeps=[sweep],
    )
    sig = SilverBullet().evaluate(snap, now, bars)
    assert sig is not None
    assert sig.setup == "silver_bullet" and sig.side == Side.BUY
    assert sig.rr >= Decimal("1.5")
    assert sig.confluence == {
        "bias": True,
        "fvg": True,
        "ob": False,
        "mss": True,
        "sweep": True,
    }


def test_sb_outside_window_returns_none() -> None:
    now = datetime(2024, 6, 5, 12, 0, tzinfo=UTC)
    bars = _bars_sb()
    snap = StructureSnapshot(
        symbol=Symbol("EURUSD"),
        at=now,
        bias=Bias.BULL,
        zones=[],
        swings=[],
        sweeps=[],
    )
    assert SilverBullet().evaluate(snap, now, bars) is None


def test_sb_no_bias_none() -> None:
    now = datetime(2024, 6, 5, 7, 55, tzinfo=UTC)
    bars = _bars_sb()
    snap = StructureSnapshot(
        symbol=Symbol("EURUSD"),
        at=now,
        bias=Bias.NONE,
        zones=[],
        swings=[],
        sweeps=[],
    )
    assert SilverBullet().evaluate(snap, now, bars) is None
