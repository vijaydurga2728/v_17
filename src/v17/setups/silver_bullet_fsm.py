"""Silver Bullet FSM — parameterized across 6 engines per spec §4.

The FSM is the gating + signal-construction layer. Pattern detection
(sweep confirmation, displacement bar identification, FVG detection,
liquidity-pool enumeration, D1 bias) is performed by the engine_runner
(Task 5.2) and supplied via `context`. The FSM returns an SBSignal
only when all gates pass and context carries a valid confluence.

SL / TP / R:R will be wired by Task 3.9 (`compute_sl_tp`); for this
task, SL/TP/r_multiple are sentinel 0.0 and are replaced downstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from v17.setups.sb_engines import SBEngineConfig
from v17.setups.sb_constants import (
    SPREAD_GUARD_MULT,
    FVG_COST_VIABILITY_MULT,
)


Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class SBSignal:
    engine_id: str
    symbol: str
    side: Side
    ts_entry_ns: int
    entry_price: float
    sl_price: float
    tp_price: float
    r_multiple: float
    fvg_top: float
    fvg_bottom: float


_BIAS_TO_SIDE: dict[str, Side] = {"BULLISH": "LONG", "BEARISH": "SHORT"}
_BIAS_TO_FVG_KIND: dict[str, str] = {"BULLISH": "bullish", "BEARISH": "bearish"}


class SilverBulletFSM:
    def __init__(self, config: SBEngineConfig):
        self._config = config

    @property
    def engine_id(self) -> str:
        return self._config.engine_id

    @property
    def entry_model(self) -> str:
        return self._config.entry_model

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._config.symbols

    @property
    def window_ny(self) -> tuple[str, str]:
        return self._config.window_ny

    def step(self, bar: dict, context: dict) -> SBSignal | None:
        bias = context.get("d1_bias", "NONE")
        if bias == "NONE":
            return None
        if context.get("calendar_blackout", False):
            return None
        if not context.get("window_open", False):
            return None
        spread = float(context.get("spread", 0.0))
        median = float(context.get("spread_median", 0.0) or 0.0)
        if median > 0 and spread > SPREAD_GUARD_MULT * median:
            return None
        if not context.get("sweep_confirmed", False):
            return None
        fvg = context.get("displacement_bar_fvg")
        if fvg is None:
            return None
        expected_kind = _BIAS_TO_FVG_KIND[bias]
        if fvg.get("kind") != expected_kind:
            return None
        top = float(fvg["top"])
        bottom = float(fvg["bottom"])
        height = top - bottom
        if spread > 0 and height < FVG_COST_VIABILITY_MULT * spread:
            return None
        side: Side = _BIAS_TO_SIDE[bias]
        if self._config.entry_model == "CE":
            entry = float(fvg.get("ce", (top + bottom) / 2.0))
        else:  # AGGRESSIVE: proximal edge
            # LONG enters at top (buyer reaches up to FVG upper edge);
            # SHORT enters at bottom (seller reaches down to FVG lower edge).
            entry = top if side == "LONG" else bottom
        return SBSignal(
            engine_id=self._config.engine_id,
            symbol=str(bar["symbol"]),
            side=side,
            ts_entry_ns=int(bar["ts_utc"]),
            entry_price=entry,
            sl_price=0.0,  # placeholder; Task 3.9 wires compute_sl_tp
            tp_price=0.0,
            r_multiple=0.0,
            fvg_top=top,
            fvg_bottom=bottom,
        )
