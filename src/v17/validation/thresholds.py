from __future__ import annotations

from typing import Final

VALIDATION_THRESHOLDS: Final[dict[str, float]] = {
    "min_pf": 1.8,
    "min_sharpe": 2.0,
    "max_dd_pct": 6.0,
    "min_winrate": 0.50,
    "min_mc_p5_pf": 1.3,
    "max_mc_p95_dd_pct": 8.0,
    "min_oos_trades": 200,
    "min_folds_passed": 4,
}
