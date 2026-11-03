from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

import pandas as pd

from v17.backtest.cost import (
    MIN_PIP_SL_BY_SYMBOL,
    TP_FALLBACK_PIPS_BY_SYMBOL,
    ZONE_TOLERANCE_BY_SYMBOL,
    pip_size,
)
from v17.common.dtos import Signal, StructureSnapshot, Zone
from v17.common.types import TF, Bias, Side
from v17.setups.judas_swing import _swept_asian_extreme
from v17.setups.sessions import asian_high_low, in_silver_bullet_window
from v17.setups.signal_id import make_signal_id
from v17.setups.targets import passes_rr, pip_distance, rr

MIN_PIP_SL: Final = Decimal("2")
TP_FALLBACK_PIPS: Final = Decimal("22")
SWEEP_LOOKBACK_MIN: Final = 90
MSS_LOOKBACK_MIN: Final = 30
ZONE_TOLERANCE_PIPS: Final = Decimal("10")
# _PIP is now symbol-dependent via pip_size(). Kept as fallback for FX majors.
_PIP: Final = Decimal("0.0001")


class SilverBullet:
    name = "silver_bullet"

    def __init__(
        self,
        min_pip_sl: Decimal = MIN_PIP_SL,
        tp_fallback_pips: Decimal = TP_FALLBACK_PIPS,
        require_sweep: bool = True,
        require_mss: bool = True,
    ) -> None:
        self.min_pip_sl = min_pip_sl
        self.tp_fallback_pips = tp_fallback_pips
        self.require_sweep = require_sweep
        self.require_mss = require_mss

    def evaluate(
        self, snap: StructureSnapshot, now: datetime, bars_1m: pd.DataFrame
    ) -> Signal | None:
        if not in_silver_bullet_window(now):
            return None
        if snap.bias == Bias.NONE:
            return None
        side = Side.BUY if snap.bias == Bias.BULL else Side.SELL

        last_close = Decimal(str(float(bars_1m["close"].iloc[-1])))
        zone = _pick_zone(snap.zones, side, last_close, now, snap.symbol)
        if zone is None:
            return None

        want_sweep = "ssl" if side == Side.BUY else "bsl"
        recent_sweeps = [
            s
            for s in snap.sweeps
            if s.kind == want_sweep
            and (now - s.at) <= timedelta(minutes=SWEEP_LOOKBACK_MIN)
        ]
        sweep_ok = len(recent_sweeps) > 0
        sweep_extreme: Decimal | None = recent_sweeps[-1].level if recent_sweeps else None

        if not sweep_ok:
            try:
                asian_hi, asian_lo = asian_high_low(bars_1m, now)
                if side == Side.BUY:
                    swept_a, extreme_a = _swept_asian_extreme(bars_1m, now, asian_lo, direction="down")
                else:
                    swept_a, extreme_a = _swept_asian_extreme(bars_1m, now, asian_hi, direction="up")
                if swept_a:
                    sweep_ok = True
                    sweep_extreme = extreme_a
            except Exception:
                pass

        if self.require_sweep and not sweep_ok:
            return None

        mss_ok = any(
            sw.kind == "mss"
            and sw.side == side
            and sw.tf == TF.M1
            and (now - sw.at) <= timedelta(minutes=MSS_LOOKBACK_MIN)
            for sw in snap.swings
        )
        if self.require_mss and not mss_ok:
            return None

        pip = pip_size(snap.symbol)
        entry = (zone.top + zone.bottom) / 2
        if side == Side.BUY:
            sweep_level = sweep_extreme if sweep_extreme is not None else zone.bottom
            sl = min(sweep_level, zone.bottom) - pip
            risk = entry - sl
            if risk <= 0:
                return None
            # Standard ICT Silver Bullet universal 1:2 R:R expansion target
            tp = entry + (risk * Decimal("2.0"))
        else:
            sweep_level = sweep_extreme if sweep_extreme is not None else zone.top
            sl = max(sweep_level, zone.top) + pip
            risk = sl - entry
            if risk <= 0:
                return None
            tp = entry - (risk * Decimal("2.0"))

        min_sl = MIN_PIP_SL_BY_SYMBOL.get(snap.symbol, self.min_pip_sl)
        risk_pips = pip_distance(entry, sl, symbol=snap.symbol)
        if risk_pips < min_sl:
            return None
        max_sl = (
            Decimal("30")
            if snap.symbol.endswith("IDXUSD")
            else (Decimal("20") if "JPY" in snap.symbol else Decimal("15"))
        )
        if risk_pips > max_sl:
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
    zones: list[Zone],
    side: Side,
    last_close: Decimal,
    now: datetime,
    symbol: str | None = None,
) -> Zone | None:
    if symbol is not None:
        tol_pips = ZONE_TOLERANCE_BY_SYMBOL.get(symbol, ZONE_TOLERANCE_PIPS)
        tol = tol_pips * pip_size(symbol)
    else:
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
