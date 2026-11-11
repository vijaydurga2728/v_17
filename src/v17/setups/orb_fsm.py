"""ORB Reversal FSM.

States:
  IDLE -> OR_BUILDING -> OR_LOCKED -> BREAKOUT_DETECTED
       -> REVERSAL_CONFIRMED -> ENTRY_ARMED -> MANAGED -> EXIT

Transitions (all time comparisons in ns UTC):
  * start_day -> IDLE; or_high/or_low cleared.
  * bar inside OR window -> OR_BUILDING; track rolling high/low.
  * bar at/after OR window end  -> OR_LOCKED; or_high/or_low frozen.
  * bar closes outside OR after lock -> BREAKOUT_DETECTED; side = fade of break.
  * within REVERSAL_CONFIRM_MAX_MIN after breakout, a bar closes BACK inside
    [or_low, or_high] -> REVERSAL_CONFIRMED -> ENTRY_ARMED; emit ORBSignal.
  * no close-back-inside within window -> EXIT (day done, no signal).

Runner is responsible for the post-emit MANAGED/EXIT walk (fills + VWAP trail).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

from v17.setups.orb_constants import REVERSAL_CONFIRM_MAX_MIN


Side = Literal["long", "short"]
Phase = Literal[
    "IDLE",
    "OR_BUILDING",
    "OR_LOCKED",
    "BREAKOUT_DETECTED",
    "REVERSAL_CONFIRMED",
    "ENTRY_ARMED",
    "MANAGED",
    "EXIT",
]

_NS_PER_MIN = 60_000_000_000


@dataclass
class ORBSignal:
    side: Side
    stop_price: float          # OR extreme (short: or_high, long: or_low)
    armed_ns: int
    armed_bar_idx: int


@dataclass
class ORBState:
    phase: Phase = "IDLE"
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    or_lock_ns: Optional[int] = None
    breakout_side: Optional[Side] = None
    breakout_ns: Optional[int] = None
    day_signal_emitted: bool = False


class ORBFSM:
    """Stateful FSM operating on pre-indexed M1 bars.

    Caller passes a session-sliced DataFrame with columns:
      ts_ns (int64), open, high, low, close (float), plus optional volume.
    Caller determines OR window start/end ns and session end ns.
    """

    def __init__(
        self,
        or_start_ns: int,
        or_end_ns: int,
        session_end_ns: int,
    ) -> None:
        self.or_start_ns = int(or_start_ns)
        self.or_end_ns = int(or_end_ns)
        self.session_end_ns = int(session_end_ns)
        self.state = ORBState()

    # ------------------------------------------------------------------ API
    def start_day(self) -> None:
        self.state = ORBState()

    def on_bar(self, bar: pd.Series, bar_idx: int) -> Optional[ORBSignal]:
        """Advance the FSM one bar. Returns an ORBSignal when armed, else None."""
        if self.state.day_signal_emitted or self.state.phase == "EXIT":
            return None

        ts = int(bar["ts_ns"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        # OR window: build / lock
        if ts < self.or_start_ns:
            return None
        if self.or_start_ns <= ts < self.or_end_ns:
            self._update_or(high, low)
            self.state.phase = "OR_BUILDING"
            return None

        # First bar at or after OR end — lock OR if still building.
        if self.state.phase in ("IDLE", "OR_BUILDING"):
            if self.state.or_high is None or self.state.or_low is None:
                # No OR formed (no bars inside window). Dead day.
                self.state.phase = "EXIT"
                return None
            self.state.phase = "OR_LOCKED"
            self.state.or_lock_ns = self.or_end_ns

        # Past session end — close out.
        if ts > self.session_end_ns:
            self.state.phase = "EXIT"
            return None

        # Look for breakout.
        if self.state.phase == "OR_LOCKED":
            if close > self.state.or_high:  # type: ignore[operator]
                self.state.phase = "BREAKOUT_DETECTED"
                self.state.breakout_side = "short"  # fade the up-break
                self.state.breakout_ns = ts
            elif close < self.state.or_low:  # type: ignore[operator]
                self.state.phase = "BREAKOUT_DETECTED"
                self.state.breakout_side = "long"  # fade the down-break
                self.state.breakout_ns = ts
            return None

        # Look for close-back-inside within confirm window.
        if self.state.phase == "BREAKOUT_DETECTED":
            assert self.state.breakout_ns is not None
            assert self.state.or_high is not None
            assert self.state.or_low is not None
            elapsed_min = (ts - self.state.breakout_ns) / _NS_PER_MIN
            inside = self.state.or_low <= close <= self.state.or_high
            if inside:
                side: Side = self.state.breakout_side  # type: ignore[assignment]
                stop_price = self.state.or_high if side == "short" else self.state.or_low
                self.state.phase = "ENTRY_ARMED"
                self.state.day_signal_emitted = True
                return ORBSignal(
                    side=side,
                    stop_price=float(stop_price),
                    armed_ns=ts,
                    armed_bar_idx=bar_idx,
                )
            if elapsed_min > REVERSAL_CONFIRM_MAX_MIN:
                self.state.phase = "EXIT"
            return None

        return None

    # ------------------------------------------------------------- helpers
    def _update_or(self, high: float, low: float) -> None:
        if self.state.or_high is None or high > self.state.or_high:
            self.state.or_high = high
        if self.state.or_low is None or low < self.state.or_low:
            self.state.or_low = low
