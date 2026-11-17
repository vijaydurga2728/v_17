"""Cycle 9 12-slot grid driver (pre-reg §9, §12 Tier 1)."""
from __future__ import annotations

import pandas as pd

from v17.backtest.c9_runner import Prepared, metrics, run_slot, tier1_pass
from v17.setups.c9_pdh_pdl import all_slots


def run_grid(
    prep: Prepared, slippage_pts: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Run all 12 slots. Returns (report, trades_by_slot_id)."""
    rows = []
    trades: dict[str, pd.DataFrame] = {}
    for idx, slot in enumerate(all_slots()):
        tl = run_slot(prep, slot, slippage_pts)
        trades[slot.slot_id] = tl
        m = metrics(tl["r"].to_numpy())
        rows.append({
            "slot_index": idx, "slot_id": slot.slot_id, "sweep_buffer": slot.sweep_buffer,
            "direction": slot.direction, "n_conf": slot.n_conf, "slippage_pts": slippage_pts,
            **m, "tier1_pass": tier1_pass(m),
        })
    return pd.DataFrame(rows), trades
