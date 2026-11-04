"""Per-engine OOS runner scaffold.

Stage 1 (this task): iterates OOS bars and asks the FSM for a signal
with a MINIMAL context (d1_bias NONE, no sweep, no FVG) so all gates
reject. Signals land as [] for every call.

Stage 2 (Task 5.3): wires full context — D1 bias from compute_d1_bias,
ATR_14 from rolling true-range, FVGs from fvg_sb.detect_fvgs_at,
pools from liquidity_pools.enumerate_pools, sweep-confirmation logic,
calendar blackout + spread guard. Trades begin to fire in Stage 2.

Stage 3 (Task 3.9 wire): SL/TP replacement via compute_sl_tp. Stage 1
leaves SBSignal fields SL/TP = 0.0.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from v17.setups.silver_bullet_fsm import SilverBulletFSM
from v17.setups.sb_engines import SBEngineConfig
from v17.backtest.walkforward import Fold


@dataclass
class TradeLog:
    engine_id: str
    fold_id: int
    trades: list = field(default_factory=list)


def _empty_context() -> dict:
    return {
        "d1_bias": "NONE",
        "atr_14": 0.0,
        "spread": 0.0,
        "spread_median": 0.0,
        "calendar_blackout": False,
        "window_open": False,
        "liquidity_pools": [],
        "fvgs": [],
        "sweep_confirmed": False,
        "swept_pool_kind": None,
        "displacement_bar_fvg": None,
    }


def run_engine_oos(config: SBEngineConfig, bars: pd.DataFrame,
                   calendar: pd.DataFrame, fold: Fold) -> TradeLog:
    """Execute one engine over one fold's OOS window across its eligible symbols.

    Scaffold stage: FSM is called with empty context (gates reject). Task 5.3
    wires real context from D1 bias / ATR / FVGs / pools / blackout / spread.
    """
    log = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
    fsm = SilverBulletFSM(config)
    for symbol in config.symbols:
        sym_bars = bars[
            (bars["symbol"] == symbol)
            & (bars["ts_utc"] >= fold.oos_start)
            & (bars["ts_utc"] < fold.oos_end)
        ]
        if sym_bars.empty:
            continue
        for _, row in sym_bars.iterrows():
            bar = row.to_dict()
            sig = fsm.step(bar, _empty_context())
            if sig is not None:
                log.trades.append(sig)
    return log
