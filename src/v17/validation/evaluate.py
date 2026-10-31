from __future__ import annotations

from v17.common.dtos import RunReport
from v17.validation.thresholds import VALIDATION_THRESHOLDS


def evaluate(
    report: RunReport,
    thresholds: dict[str, float] = VALIDATION_THRESHOLDS,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if report.pf < thresholds["min_pf"]:
        reasons.append(f"pf {report.pf:.2f} < {thresholds['min_pf']}")
    if report.sharpe < thresholds["min_sharpe"]:
        reasons.append(f"sharpe {report.sharpe:.2f} < {thresholds['min_sharpe']}")
    if report.max_dd_pct >= thresholds["max_dd_pct"]:
        reasons.append(f"max_dd {report.max_dd_pct:.2f}% >= {thresholds['max_dd_pct']}%")
    if report.winrate < thresholds["min_winrate"]:
        reasons.append(f"winrate {report.winrate:.2f} < {thresholds['min_winrate']}")
    if report.oos_pf < thresholds["min_pf"]:
        reasons.append(f"oos_pf {report.oos_pf:.2f} < {thresholds['min_pf']}")
    if report.oos_sharpe < thresholds["min_sharpe"]:
        reasons.append(f"oos_sharpe {report.oos_sharpe:.2f} < {thresholds['min_sharpe']}")
    if report.oos_max_dd_pct >= thresholds["max_dd_pct"]:
        reasons.append(
            f"oos_max_dd {report.oos_max_dd_pct:.2f}% >= {thresholds['max_dd_pct']}%"
        )
    if report.oos_trades < thresholds["min_oos_trades"]:
        reasons.append(
            f"oos_trades {report.oos_trades} < {int(thresholds['min_oos_trades'])}"
        )
    if report.mc_p5_pf < thresholds["min_mc_p5_pf"]:
        reasons.append(f"mc_p5_pf {report.mc_p5_pf:.2f} < {thresholds['min_mc_p5_pf']}")
    if report.mc_p95_max_dd_pct > thresholds["max_mc_p95_dd_pct"]:
        reasons.append(
            f"mc_p95_max_dd {report.mc_p95_max_dd_pct:.2f}% > "
            f"{thresholds['max_mc_p95_dd_pct']}%"
        )
    if report.walkforward_folds_passed < thresholds["min_folds_passed"]:
        reasons.append(
            f"folds_passed {report.walkforward_folds_passed} < "
            f"{int(thresholds['min_folds_passed'])}"
        )
    return (len(reasons) == 0, reasons)
