from __future__ import annotations

from decimal import Decimal
from typing import Final

RISK: Final[dict[str, object]] = {
    "per_trade_pct": Decimal("0.5"),
    "min_rr": Decimal("1.5"),
    "min_pip_sl": Decimal("2"),
    "max_concurrent_positions": 1,
    "max_trades_per_day": 3,
    "symbols": ("EURUSD", "GBPUSD", "USDJPY", "EURGBP", "USATECHIDXUSD"),
    "pip_value_per_lot_usd": Decimal("10"),
    "min_lot": Decimal("0.01"),
    "lot_step": Decimal("0.01"),
}
