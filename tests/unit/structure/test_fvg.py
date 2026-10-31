from decimal import Decimal
from pathlib import Path

import pandas as pd

from v17.common.types import TF, Side
from v17.structure.fvg import detect_fvgs

FIX = Path(__file__).parent.parent.parent / "fixtures" / "structure"


def _load(name: str) -> pd.DataFrame:
    df = pd.read_csv(FIX / name)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def test_detect_bull_fvg() -> None:
    df = _load("fvg_bull.csv")
    zones = detect_fvgs(df, TF.M15)
    assert len(zones) >= 1
    z = zones[0]
    assert z.kind == "fvg" and z.side == Side.BUY and z.tf == TF.M15
    assert z.top == Decimal("1.1015") and z.bottom == Decimal("1.101")


def test_detect_bear_fvg_count() -> None:
    df = _load("fvg_bear.csv")
    zones = detect_fvgs(df, TF.M15)
    assert any(z.side == Side.SELL for z in zones)
