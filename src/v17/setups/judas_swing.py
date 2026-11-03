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
from v17.setups.sessions import asian_high_low, in_judas_window
from v17.setups.signal_id import make_signal_id
from v17.setups.targets import passes_rr, pip_distance, rr

MIN_PIP_SL: Final = Decimal("2")
TP_FALLBACK_PIPS: Final = Decimal("22")
MSS_LOOKBACK_MIN: Final = 30
SWEEP_LOOKBACK_MIN: Final = 60
ZONE_TOLERANCE_PIPS: Final = Decimal("10")
# _PIP is symbol-dependent via pip_size(); kept as FX-major fallback.
_PIP: Final = Decimal("0.0001")


class JudasSwing:
    name = "judas_swing"

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
        if snap.symbol.endswith("IDXUSD"):
            # US Indices are NY-session instruments; London Judas swing has no institutional volume.
            return None
        if not in_judas_window(now):
            return None
        if snap.bias == Bias.NONE:
            return None
        side = Side.BUY if snap.bias == Bias.BULL else Side.SELL

        try:
            asian_hi, asian_lo = asian_high_low(bars_1m, now)
            scale = 100 if "JPY" in snap.symbol else 10000
            if (asian_hi - asian_lo) * scale > 30.0:
                # Authentic ICT: Asian range must be consolidation (<= 30 pips)
                return None
        except ValueError:
            return None

        # sweep direction opposite to bias (Judas = fake move against bias then reversal)
        if side == Side.BUY:
            # bias bullish → look for a sweep of Asian low that closed back above
            swept, sweep_extreme = _swept_asian_extreme(bars_1m, now, asian_lo, direction="down")
        else:
            swept, sweep_extreme = _swept_asian_extreme(bars_1m, now, asian_hi, direction="up")
        if self.require_sweep and not swept:
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

        last_close = Decimal(str(float(bars_1m["close"].iloc[-1])))
        zone = _pick_zone(snap.zones, side, last_close, now, snap.symbol)
        if zone is None:
            return None

        pip = pip_size(snap.symbol)
        entry = (zone.top + zone.bottom) / 2
        if side == Side.BUY:
            base_sl = sweep_extreme if sweep_extreme is not None else Decimal(str(asian_lo))
            sl = min(base_sl, zone.bottom) - pip
            risk = entry - sl
            if risk <= 0:
                return None
            target = Decimal(str(asian_hi))
            rr_target = (target - entry) / risk
            if rr_target >= Decimal("1.5"):
                tp = target
            else:
                tp = entry + (risk * Decimal("2.0"))
        else:
            base_sl = sweep_extreme if sweep_extreme is not None else Decimal(str(asian_hi))
            sl = max(base_sl, zone.top) + pip
            risk = sl - entry
            if risk <= 0:
                return None
            target = Decimal(str(asian_lo))
            rr_target = (entry - target) / risk
            if rr_target >= Decimal("1.5"):
                tp = target
            else:
                tp = entry - (risk * Decimal("2.0"))

        min_sl = MIN_PIP_SL_BY_SYMBOL.get(snap.symbol, self.min_pip_sl)
        if pip_distance(entry, sl, symbol=snap.symbol) < min_sl:
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


def _swept_asian_extreme(
    bars_1m: pd.DataFrame, now: datetime, level: float, direction: str
) -> tuple[bool, Decimal | None]:
    window_start = now - timedelta(minutes=SWEEP_LOOKBACK_MIN)
    m = (bars_1m["ts"] >= pd.Timestamp(window_start)) & (bars_1m["ts"] <= pd.Timestamp(now))
    sub = bars_1m[m]
    if sub.empty:
        return False, None
    if direction == "down":
        poked = (sub["low"] < level).any()
        reclaimed = float(sub["close"].iloc[-1]) >= level or ((sub["low"] < level) & (sub["close"] > level)).any()
        if not (poked and reclaimed):
            return False, None
        extreme = Decimal(str(float(sub["low"].min())))
        return True, extreme
    else:
        poked = (sub["high"] > level).any()
        reclaimed = float(sub["close"].iloc[-1]) <= level or ((sub["high"] > level) & (sub["close"] < level)).any()
        if not (poked and reclaimed):
            return False, None
        extreme = Decimal(str(float(sub["high"].max())))
        return True, extreme
