"""Cycle 6 daily circuit-breaker state machine."""
from __future__ import annotations

from dataclasses import dataclass

from v17.setups.c6_constants import (
    HARD_LOSS_PCT, MAX_CONSEC_LOSSES, MAX_TRADES_PER_DAY,
    PROFIT_STOP_PCT, SOFT_LOSS_PCT,
)


@dataclass
class DailyState:
    utc_date: str
    equity_sod: float
    realized_pnl: float
    trade_count: int
    consec_losses: int
    locked: bool
    flatten_now: bool


def update_after_trade(state: DailyState, trade_pnl: float) -> DailyState:
    state.realized_pnl += trade_pnl
    state.trade_count += 1
    if trade_pnl <= 0:
        state.consec_losses += 1
    else:
        state.consec_losses = 0
    return state


def evaluate(state: DailyState) -> DailyState:
    pnl_pct = state.realized_pnl / state.equity_sod if state.equity_sod > 0 else 0.0
    state.flatten_now = False
    # Precedence: hard-loss > profit > soft-loss > consec > trade-cap.
    if pnl_pct <= HARD_LOSS_PCT:
        state.flatten_now = True
        state.locked = True
    elif pnl_pct >= PROFIT_STOP_PCT:
        state.flatten_now = True
        state.locked = True
    elif pnl_pct <= SOFT_LOSS_PCT:
        state.locked = True
    elif state.consec_losses >= MAX_CONSEC_LOSSES:
        state.locked = True
    elif state.trade_count >= MAX_TRADES_PER_DAY:
        state.locked = True
    return state


def allow_entry(state: DailyState) -> bool:
    return not state.locked
