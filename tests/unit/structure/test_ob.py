from decimal import Decimal
from pathlib import Path

import pandas as pd

from v17.common.types import TF, Side
from v17.structure.ob import detect_obs

FIX = Path(__file__).parent.parent.parent / "fixtures" / "structure"


def _load(name: str) -> pd.DataFrame:
    df = pd.read_csv(FIX / name)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def test_detect_bull_ob() -> None:
    df = _load("ob_bull.csv")
    zones = detect_obs(df, TF.M15, atr_mult=2.0)
    bulls = [z for z in zones if z.side == Side.BUY and z.kind == "ob"]
    assert len(bulls) >= 1
    z = bulls[0]
    assert z.top == Decimal("1.1001")
    assert z.bottom == Decimal("1.0995")
