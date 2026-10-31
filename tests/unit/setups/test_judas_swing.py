from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from v17.common.dtos import StructureSnapshot, Swing, Zone
from v17.common.types import TF, Bias, Side, Symbol
from v17.setups.judas_swing import JudasSwing


def _bars_judas() -> pd.DataFrame:
    # Build 1m bars from Asian session (23:00 UTC prev day) through 06:30 UTC (Judas window)
    ts_asian = pd.date_range("2024-06-04 23:00", periods=420, freq="1min", tz="UTC")
    base_asian = 1.0850 + np.linspace(0, 0.0005, 420)
    asian = pd.DataFrame(
        {
            "ts": ts_asian,
            "open": base_asian,
            "high": base_asian + 0.0003,
            "low": base_asian - 0.0003,
            "close": base_asian,
            "volume": np.ones(420, dtype="int64"),
            "spread_pips": np.full(420, 0.5),
        }
    )
    # Asian high ~ 1.0858, low ~ 1.0847
    # Judas window from 06:00 UTC = 07:00 London BST; add 60 bars 06:00..06:59
    ts_j = pd.date_range("2024-06-05 06:00", periods=60, freq="1min", tz="UTC")
    base_j = np.full(60, 1.0850)
    highs_j = base_j + 0.0003
    lows_j = base_j - 0.0003
    opens_j = base_j
    closes_j = base_j.copy()
    # at index 20 (06:20 UTC) sweep Asian low: wick below 1.0847, close back above
    lows_j[20] = 1.0845
    closes_j[20] = 1.0850
    # at index 30 price returns into bull FVG zone created around 1.0852
    for i in range(30, 60):
        base_j[i] = 1.0852
        opens_j[i] = 1.0852
        closes_j[i] = 1.0852
        highs_j[i] = 1.08525
        lows_j[i] = 1.08515
    judas = pd.DataFrame(
        {
            "ts": ts_j,
            "open": opens_j,
            "high": highs_j,
            "low": lows_j,
            "close": closes_j,
            "volume": np.ones(60, dtype="int64"),
            "spread_pips": np.full(60, 0.5),
        }
    )
    return pd.concat([asian, judas], ignore_index=True)


def test_judas_bull_signal() -> None:
    now = datetime(2024, 6, 5, 6, 30, tzinfo=UTC)
    bars = _bars_judas()
    zone = Zone(
        kind="fvg",
        side=Side.BUY,
        tf=TF.M15,
        created_at=datetime(2024, 6, 5, 5, 45, tzinfo=UTC),
        top=Decimal("1.0855"),
        bottom=Decimal("1.0849"),
    )
    mss = Swing(
        kind="mss",
        side=Side.BUY,
        tf=TF.M1,
        at=datetime(2024, 6, 5, 6, 28, tzinfo=UTC),
        price=Decimal("1.0851"),
    )
    snap = StructureSnapshot(
        symbol=Symbol("EURUSD"),
        at=now,
        bias=Bias.BULL,
        zones=[zone],
        swings=[mss],
        sweeps=[],
    )
    sig = JudasSwing().evaluate(snap, now, bars)
    assert sig is not None
    assert sig.setup == "judas_swing" and sig.side == Side.BUY
    assert sig.rr >= Decimal("1.5")


def test_judas_outside_window_none() -> None:
    now = datetime(2024, 6, 5, 12, 0, tzinfo=UTC)
    bars = _bars_judas()
    snap = StructureSnapshot(
        symbol=Symbol("EURUSD"),
        at=now,
        bias=Bias.BULL,
        zones=[],
        swings=[],
        sweeps=[],
    )
    assert JudasSwing().evaluate(snap, now, bars) is None
