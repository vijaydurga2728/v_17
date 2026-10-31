from __future__ import annotations

from decimal import Decimal
from typing import Final

FTMO_CHALLENGE_100K: Final[dict[str, object]] = {
    "account_size": Decimal("100000"),
    "profit_target_phase1_pct": Decimal("10.0"),
    "profit_target_phase2_pct": Decimal("5.0"),
    "max_daily_loss_pct": Decimal("5.0"),
    "soft_daily_stop_pct": Decimal("4.0"),
    "max_overall_dd_pct": Decimal("10.0"),
    "min_trading_days": 4,
    "consistency_best_day_pct_of_profit": Decimal("30.0"),
    "news_trading_allowed": True,
    "weekend_hold_allowed": True,
    "ea_allowed": True,
    "forbidden": ("HFT", "grid", "martingale", "copy", "latency_arb"),
}


FTMO_CHALLENGE_10K: Final[dict[str, object]] = {
    "account_size": Decimal("10000"),
    "profit_target_phase1_pct": Decimal("10.0"),
    "profit_target_phase2_pct": Decimal("5.0"),
    "max_daily_loss_pct": Decimal("5.0"),
    "soft_daily_stop_pct": Decimal("4.0"),
    "max_overall_dd_pct": Decimal("10.0"),
    "min_trading_days": 4,
    "consistency_best_day_pct_of_profit": Decimal("30.0"),
    "news_trading_allowed": True,
    "weekend_hold_allowed": True,
    "ea_allowed": True,
    "forbidden": ("HFT", "grid", "martingale", "copy", "latency_arb"),
}
