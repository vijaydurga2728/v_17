"""Float-based instrument helpers for the Silver Bullet engine.

Keeps symmetry with `v17.backtest.cost.pip_size` (Decimal) but exposes
float for FSM / backtest hot paths that avoid Decimal overhead.
"""
from __future__ import annotations

_PIP_SCALE: dict[str, int] = {
    "EURUSD": 10000,
    "GBPUSD": 10000,
    "EURGBP": 10000,
    "AUDUSD": 10000,
    "USDCAD": 10000,
    "USDCHF": 10000,
    "NZDUSD": 10000,
    "USDJPY": 100,
    "USATECHIDXUSD": 1,
    "USA500IDXUSD": 1,
    "USA30IDXUSD": 1,
    "BTCUSD": 1,
    "XAUUSD": 10,  # gold: 0.1 price = 1 pip
}


def pip_size(symbol: str) -> float:
    """Return one pip in price units for a symbol. Defaults to FX (0.0001) for unknown."""
    scale = _PIP_SCALE.get(symbol, 10000)
    return 1.0 / scale
