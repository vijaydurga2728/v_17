"""Cycle 6 two-leg position state machine."""
from __future__ import annotations

from dataclasses import dataclass, field

from v17.setups.c6_constants import TRAIL_BUFFER_ATR_MULT


@dataclass
class C6Position:
    trade_id: str
    symbol: str
    side: str  # "long" | "short"
    entry_ts_ns: int
    entry_price: float
    initial_stop: float
    r_price: float
    lots_a: float
    lots_b: float
    leg_a_open: bool
    leg_b_open: bool
    leg_b_stop: float
    breakeven_hit: bool
    exit_log: list[dict] = field(default_factory=list)


def _target_price(pos: C6Position) -> float:
    return pos.entry_price + pos.r_price if pos.side == "long" else pos.entry_price - pos.r_price


def _hit_target(pos: C6Position, bar: dict) -> bool:
    tgt = _target_price(pos)
    if pos.side == "long":
        return bar["bid_h"] >= tgt
    return bar["bid_l"] <= tgt


def _hit_stop(pos: C6Position, bar: dict, stop: float) -> bool:
    if pos.side == "long":
        return bar["bid_l"] <= stop
    return bar["bid_h"] >= stop


def step(pos: C6Position, bar: dict, ema20: float, atr: float, is_hard_flat: bool) -> C6Position:
    if is_hard_flat:
        price = bar["bid_c"] if pos.side == "long" else bar["ask_c"]
        if pos.leg_a_open:
            pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "A", "reason": "time_stop", "price": price, "lots": pos.lots_a})
            pos.leg_a_open = False
        if pos.leg_b_open:
            pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "B", "reason": "time_stop", "price": price, "lots": pos.lots_b})
            pos.leg_b_open = False
        return pos

    # Initial stop: both legs out if either still on initial stop.
    if pos.leg_a_open and _hit_stop(pos, bar, pos.initial_stop):
        price = pos.initial_stop
        pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "A", "reason": "initial_stop", "price": price, "lots": pos.lots_a})
        pos.leg_a_open = False
        if pos.leg_b_open and not pos.breakeven_hit:
            pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "B", "reason": "initial_stop", "price": price, "lots": pos.lots_b})
            pos.leg_b_open = False
        return pos

    # Leg-A target.
    leg_a_filled_this_bar = False
    if pos.leg_a_open and _hit_target(pos, bar):
        price = _target_price(pos)
        pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "A", "reason": "target_1R", "price": price, "lots": pos.lots_a})
        pos.leg_a_open = False
        pos.breakeven_hit = True
        pos.leg_b_stop = pos.entry_price  # move leg B to BE
        leg_a_filled_this_bar = True

    # Leg-B trail (only after leg A filled / breakeven set; not the same bar leg A fills).
    if pos.leg_b_open and pos.breakeven_hit and not leg_a_filled_this_bar:
        if pos.side == "long":
            proposed = ema20 - TRAIL_BUFFER_ATR_MULT * atr
            if proposed > pos.leg_b_stop:
                pos.leg_b_stop = proposed
        else:
            proposed = ema20 + TRAIL_BUFFER_ATR_MULT * atr
            if proposed < pos.leg_b_stop:
                pos.leg_b_stop = proposed

    # Leg-B stop check (trailed or breakeven).
    if pos.leg_b_open and _hit_stop(pos, bar, pos.leg_b_stop):
        price = pos.leg_b_stop
        reason = "trail_stop" if pos.breakeven_hit and pos.leg_b_stop != pos.initial_stop else "initial_stop"
        pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "B", "reason": reason, "price": price, "lots": pos.lots_b})
        pos.leg_b_open = False

    return pos
