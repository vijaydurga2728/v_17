import numpy as np
import pandas as pd

from v17.common.types import TF
from v17.structure.liquidity import detect_sweeps


def _frame_with_swept_high() -> pd.DataFrame:
    # 40 bars: build an up-then-down swing high ~bar 20, then a sweep bar after
    n = 50
    ts = pd.date_range("2024-06-01", periods=n, freq="15min", tz="UTC")
    base = np.concatenate(
        [
            np.linspace(1.1000, 1.1050, 20),
            np.linspace(1.1050, 1.1000, 20),
            np.array(
                [1.1055, 1.1030, 1.1020, 1.1015, 1.1010,
                 1.1005, 1.1000, 1.0995, 1.0990, 1.0985]
            ),
        ]
    )[:n]
    highs = base.copy() + 0.0005
    lows = base.copy() - 0.0005
    opens = base.copy()
    closes = base.copy()
    # sweep bar at index 40: push high above swing-high level then close back below
    sweep_i = 40
    swing_high_level = 1.1055  # the local top
    highs[sweep_i] = swing_high_level + 0.001  # wick above
    closes[sweep_i] = swing_high_level - 0.0005  # close back below
    opens[sweep_i] = swing_high_level - 0.0002
    lows[sweep_i] = closes[sweep_i] - 0.0003
    return pd.DataFrame(
        {
            "ts": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.8),
        }
    )


def test_detect_bsl_sweep() -> None:
    df = _frame_with_swept_high()
    sweeps = detect_sweeps(df, TF.M15, swing_length=5)
    assert any(s.kind == "bsl" for s in sweeps)
