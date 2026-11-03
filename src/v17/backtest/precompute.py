from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd

from v17.backtest.snapshot_cache import (
    precompute_1m_choches,
    precompute_daily_ema20,
    precompute_daily_pdhl_sweeps,
)
from v17.common.dtos import StructureSnapshot, Sweep, Swing, Zone
from v17.common.types import TF, Bias, Side, Symbol
from v17.data.resample import resample
from v17.structure.bias import compute_bias_fast
from v17.structure.fvg import detect_fvgs
from v17.structure.liquidity import detect_sweeps
from v17.structure.ob import detect_obs
from v17.structure.swings import detect_swings

_MSS_WINDOW_MIN = 30


@dataclass
class PrecomputedStructure:
    symbol: Symbol
    bars_1m: pd.DataFrame
    bars_15m: pd.DataFrame
    bars_4h: pd.DataFrame
    bars_1d: pd.DataFrame
    zones_15m: list[Zone] = field(default_factory=list)
    sweeps_15m: list[Sweep] = field(default_factory=list)
    swings_4h: list[Swing] = field(default_factory=list)
    daily_ema20: pd.Series = field(default_factory=lambda: pd.Series(dtype="float64"))
    choches_1m: list[Swing] = field(default_factory=list)
    daily_cache: dict[datetime, tuple[float | None, float | None, Side | None]] = field(default_factory=dict)
    daily_pdhl_sweeps: list[tuple[pd.Timestamp, Side]] = field(default_factory=list)


def precompute(bars_1m: pd.DataFrame, symbol: Symbol) -> PrecomputedStructure:
    # Zones computed on M5 (finer grain = more candidates near price at killzone minute).
    bars_5m = resample(bars_1m, TF.M5)
    bars_15m = resample(bars_1m, TF.M15)
    bars_4h = resample(bars_1m, TF.H4)
    bars_1d = resample(bars_1m, TF.D1)
    zones = detect_fvgs(bars_5m, TF.M5) + detect_obs(bars_5m, TF.M5)
    zones.sort(key=lambda z: z.created_at)
    sweeps = detect_sweeps(bars_15m, TF.M15, swing_length=5)
    sweeps.sort(key=lambda s: s.at)
    swings = detect_swings(bars_4h, TF.H4, swing_length=3)
    swings.sort(key=lambda s: s.at)
    ema20 = precompute_daily_ema20(bars_1d)
    choches = precompute_1m_choches(bars_1m)
    pdhl_sweeps = precompute_daily_pdhl_sweeps(bars_1d)
    return PrecomputedStructure(
        symbol=symbol,
        bars_1m=bars_1m,
        bars_15m=bars_15m,
        bars_4h=bars_4h,
        bars_1d=bars_1d,
        zones_15m=zones,
        sweeps_15m=sweeps,
        swings_4h=swings,
        daily_ema20=ema20,
        choches_1m=choches,
        daily_pdhl_sweeps=pdhl_sweeps,
    )


def _last_before(seq: list[Swing], now: datetime) -> Swing | None:
    out: Swing | None = None
    for s in seq:
        if s.at <= now:
            out = s
        else:
            break
    return out


def _ema_asof(ema: pd.Series, cutoff: datetime) -> float | None:
    if ema.empty:
        return None
    sub = ema.loc[ema.index < pd.Timestamp(cutoff)]
    if sub.empty:
        return None
    return float(sub.iloc[-1])


def _mss_from_choches(
    choches: list[Swing], zones: list[Zone], now: datetime
) -> list[Swing]:
    # ICT direction confirmation only. Zone-containment is a separate confluence
    # checked at setup level by `_pick_zone`. Coupling CHoCH-location to zone
    # overlap at CHoCH-close-minute is double-counting and empirically ~0%.
    _ = zones
    if not choches:
        return []
    window_start = now - timedelta(minutes=_MSS_WINDOW_MIN)
    left = bisect.bisect_left(choches, window_start, key=lambda s: s.at)
    right = bisect.bisect_right(choches, now, key=lambda s: s.at)
    if left >= right:
        return []

    return [
        Swing(kind="mss", side=s.side, tf=s.tf, at=s.at, price=s.price)
        for s in choches[left:right]
    ]


def snapshot_at(pre: PrecomputedStructure, now: datetime) -> StructureSnapshot:
    max_age = timedelta(minutes=30 * 15)
    min_created = now - max_age

    z_left = bisect.bisect_left(pre.zones_15m, min_created, key=lambda z: z.created_at)
    z_right = bisect.bisect_right(pre.zones_15m, now, key=lambda z: z.created_at)
    zones_active = [
        z
        for z in pre.zones_15m[z_left:z_right]
        if z.mitigated_at is None or z.mitigated_at > now
    ]

    s_cutoff = now - timedelta(hours=48)
    s_left = bisect.bisect_left(pre.swings_4h, s_cutoff, key=lambda s: s.at)
    s_right = bisect.bisect_right(pre.swings_4h, now, key=lambda s: s.at)
    swings_so_far = pre.swings_4h[s_left:s_right]
    last_4h_swing = swings_so_far[-1] if swings_so_far else None
    last_4h_side: Side | None = last_4h_swing.side if last_4h_swing is not None else None

    sw_cutoff = now - timedelta(hours=12)
    sw_left = bisect.bisect_left(pre.sweeps_15m, sw_cutoff, key=lambda s: s.at)
    sw_right = bisect.bisect_right(pre.sweeps_15m, now, key=lambda s: s.at)
    sweeps_so_far = pre.sweeps_15m[sw_left:sw_right]

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if today_start in pre.daily_cache:
        ema_val, last_1d_close, pdhl_side = pre.daily_cache[today_start]
    else:
        ema_val = _ema_asof(pre.daily_ema20, today_start)
        last_1d_close = None
        bars_1d_sub = pre.bars_1d[pre.bars_1d["ts"] < pd.Timestamp(today_start)]
        if not bars_1d_sub.empty:
            last_1d_close = float(bars_1d_sub["close"].iloc[-1])

        # PDH/PDL sweep lookup: find the sweep whose usable_date == today_start
        # daily_pdhl_sweeps is sorted ascending by usable_date (pd.Timestamp)
        pdhl_side: Side | None = None
        if pre.daily_pdhl_sweeps:
            sweep_dates = [d for d, _ in pre.daily_pdhl_sweeps]
            ts_today = pd.Timestamp(today_start)
            idx = bisect.bisect_left(sweep_dates, ts_today)
            if idx < len(pre.daily_pdhl_sweeps) and sweep_dates[idx] == ts_today:
                pdhl_side = pre.daily_pdhl_sweeps[idx][1]

        pre.daily_cache[today_start] = (ema_val, last_1d_close, pdhl_side)

    bias = Bias.NONE
    if ema_val is not None and last_1d_close is not None:
        bias = compute_bias_fast(
            Decimal(str(ema_val)), Decimal(str(last_1d_close)), last_4h_side,
            pdh_pdl_side=pdhl_side,
        )

    mss = _mss_from_choches(pre.choches_1m, zones_active, now)

    return StructureSnapshot(
        symbol=pre.symbol,
        at=now,
        bias=bias,
        zones=zones_active,
        swings=swings_so_far + mss,
        sweeps=sweeps_so_far,
    )
