"""Secondary dev-phase gates (spec section 6.3)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from v17.validation.stats import compute_stats


@dataclass(frozen=True)
class GateReport:
    G1_pass: bool
    G2_pass: bool
    G3_pass: bool
    G4_pass: bool
    G5_pass: bool
    details: dict

    @property
    def all_pass(self) -> bool:
        return all([
            self.G1_pass, self.G2_pass, self.G3_pass, self.G4_pass, self.G5_pass,
        ])


def evaluate_secondary(agg_trades: pd.DataFrame, cost_stress_pf: float) -> GateReport:
    stats = compute_stats(
        agg_trades["pnl_r"].to_numpy(),
        agg_trades["ts_entry_ns"].to_numpy(),
    )
    G1 = stats.pf >= 1.3
    G2 = stats.trade_count >= 50
    per_fold = agg_trades.groupby("fold_id")["pnl_r"].sum()
    G3 = bool((per_fold > 0).all()) if len(per_fold) > 0 else False
    G4 = stats.r2 >= 0.80
    G5 = cost_stress_pf >= 1.1
    return GateReport(
        G1_pass=G1, G2_pass=G2, G3_pass=G3, G4_pass=G4, G5_pass=G5,
        details={
            "pf": stats.pf,
            "trade_count": stats.trade_count,
            "per_fold": per_fold.to_dict(),
            "r2": stats.r2,
            "cost_stress_pf": cost_stress_pf,
        },
    )
