from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

import pandas as pd

from v17.common.dtos import Signal, StructureSnapshot, Zone
from v17.common.types import TF, Bias, Side
from v17.setups.sessions import in_silver_bullet_window
from v17.setups.signal_id import make_signal_id
from v17.setups.targets import passes_rr, pip_distance, rr

MIN_PIP_SL: Final = Decimal("2")
TP_FALLBACK_PIPS: Final = Decimal("22")
SWEEP_LOOKBACK_MIN: Final = 240
MSS_LOOKBACK_MIN: Final = 30
ZONE_TOLERANCE_PIPS: Final = Decimal("10")
_PIP: Final = Decimal("0.0001")


class SilverBullet:
    name = "silver_bullet"

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
        if not in_silver_bullet_window(now):
            return None
        if snap.bias == Bias.NONE:
            return None
        side = Side.BUY if snap.bias == Bias.BULL else Side.SELL

        last_close = Decimal(str(float(bars_1m["close"].iloc[-1])))
        zone = _pick_zone(snap.zones, side, last_close, now)
        if zone is None:
            return None

        want_sweep = "ssl" if side == Side.BUY else "bsl"
        sweep_ok = any(
            s.kind == want_sweep
            and (now - s.at) <= timedelta(minutes=SWEEP_LOOKBACK_MIN)
            for s in snap.sweeps
        )
        # Sweep and MSS kept as CONFLUENCE HINTS, not gates. ICT doctrine lists
        # both as supporting evidence, not required pre-conditions.
        mss_ok = any(
            sw.kind == "mss"
            and sw.side == side
            and sw.tf == TF.M1
            and (now - sw.at) <= timedelta(minutes=MSS_LOOKBACK_MIN)
            for sw in snap.swings
        )

        entry = (zone.top + zone.bottom) / 2
        if side == Side.BUY:
            sl = zone.bottom - Decimal("0.0001")
            tp = entry + (self.tp_fallback_pips * Decimal("0.0001"))
        else:
            sl = zone.top + Decimal("0.0001")
            tp = entry - (self.tp_fallback_pips * Decimal("0.0001"))

        if pip_distance(entry, sl) < self.min_pip_sl:
            return None
        rr_ = rr(entry, sl, tp, side)
        if not passes_rr(rr_):
            return None

        return Signal(
            id=make_signal_id(snap.symbol, self.name, now, side),
            symbol=snap.symbol,
            setup="silver_bullet",
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
                "sweep": sweep_ok,
            },
            note=f"zone={zone.kind}@{zone.created_at.isoformat()}",
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
