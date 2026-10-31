from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

import pandas as pd

from v17.common.dtos import Signal, StructureSnapshot, Zone
from v17.common.types import TF, Bias, Side
from v17.setups.sessions import asian_high_low, in_judas_window
from v17.setups.signal_id import make_signal_id
from v17.setups.targets import passes_rr, pip_distance, rr

MIN_PIP_SL: Final = Decimal("2")
TP_FALLBACK_PIPS: Final = Decimal("22")
MSS_LOOKBACK_MIN: Final = 30
SWEEP_LOOKBACK_MIN: Final = 60
ZONE_TOLERANCE_PIPS: Final = Decimal("10")
_PIP: Final = Decimal("0.0001")


class JudasSwing:
    name = "judas_swing"

    def __init__(
        self,
        min_pip_sl: Decimal = MIN_PIP_SL,
        tp_fallback_pips: Decimal = TP_FALLBACK_PIPS,
    ) -> None:
        self.min_pip_sl = min_pip_sl
        self.tp_fallback_pips = tp_fallback_pips

    def evaluate(
        self, snap: StructureSnapshot, now: datetime, bars_1m: pd.DataFrame
    ) -> Signal | None:
        if not in_judas_window(now):
            return None
        if snap.bias == Bias.NONE:
            return None
        side = Side.BUY if snap.bias == Bias.BULL else Side.SELL

        try:
            asian_hi, asian_lo = asian_high_low(bars_1m, now)
        except ValueError:
            return None

        # sweep direction opposite to bias (Judas = fake move against bias then reversal)
        if side == Side.BUY:
            # bias bullish → look for a sweep of Asian low that closed back above
            swept = _swept_asian_extreme(bars_1m, now, asian_lo, direction="down")
        else:
            swept = _swept_asian_extreme(bars_1m, now, asian_hi, direction="up")
        # Sweep and MSS kept as CONFLUENCE HINTS, not gates.
        mss_ok = any(
            sw.kind == "mss"
            and sw.side == side
            and sw.tf == TF.M1
            and (now - sw.at) <= timedelta(minutes=MSS_LOOKBACK_MIN)
            for sw in snap.swings
        )

        last_close = Decimal(str(float(bars_1m["close"].iloc[-1])))
        zone = _pick_zone(snap.zones, side, last_close, now)
        if zone is None:
            return None

        entry = (zone.top + zone.bottom) / 2
        if side == Side.BUY:
            sl = Decimal(str(asian_lo)) - Decimal("0.0001")
            tp = entry + (self.tp_fallback_pips * Decimal("0.0001"))
        else:
            sl = Decimal(str(asian_hi)) + Decimal("0.0001")
            tp = entry - (self.tp_fallback_pips * Decimal("0.0001"))

        if pip_distance(entry, sl) < self.min_pip_sl:
            return None
        rr_ = rr(entry, sl, tp, side)
        if not passes_rr(rr_):
            return None

        return Signal(
            id=make_signal_id(snap.symbol, self.name, now, side),
            symbol=snap.symbol,
            setup="judas_swing",
            side=side,
            at=now,
            entry=entry,
            sl=sl,
            tp=tp,
            rr=rr_,
            confluence={
                "bias": True,
                "fvg": zone.kind == "fvg",
                "ob": zone.kind == "ob",
                "mss": mss_ok,
                "sweep": swept,
            },
            note=f"zone={zone.kind} asian_hi={asian_hi:.5f} asian_lo={asian_lo:.5f}",
        )


def _pick_zone(
    zones: list[Zone], side: Side, last_close: Decimal, now: datetime
) -> Zone | None:
    tol = ZONE_TOLERANCE_PIPS * _PIP
    best: Zone | None = None
    best_dist: Decimal | None = None
    for z in zones:
        # Lookahead-safe mitigation: zone is mitigated only if the event happened by `now`.
        if z.mitigated_at is not None and z.mitigated_at <= now:
            continue
        if z.side != side:
            continue
        if z.bottom - tol <= last_close <= z.top + tol:
            if z.bottom <= last_close <= z.top:
                dist = Decimal("0")
            elif last_close < z.bottom:
                dist = z.bottom - last_close
            else:
                dist = last_close - z.top
            if best_dist is None or dist < best_dist:
                best = z
                best_dist = dist
    return best


def _swept_asian_extreme(
    bars_1m: pd.DataFrame, now: datetime, level: float, direction: str
) -> bool:
    window_start = now - timedelta(minutes=SWEEP_LOOKBACK_MIN)
    m = (bars_1m["ts"] >= pd.Timestamp(window_start)) & (bars_1m["ts"] <= pd.Timestamp(now))
    sub = bars_1m[m]
    if sub.empty:
        return False
    if direction == "down":
        poked = (sub["low"] < level) & (sub["close"] > level)
    else:
        poked = (sub["high"] > level) & (sub["close"] < level)
    return bool(poked.any())
