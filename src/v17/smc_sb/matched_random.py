"""Spec v1.2 §3a matched control (revised R24; deliberately not called "fully matched").

Per real trade j and permutation: same side, same placement minute after 10:00, same limit offset from the
placement price, same stop and target distances; random eligible day (uniform, with replacement); identical
R13 fill, R15/R16 exits and R17 R unit; unfilled controls are redrawn (max `null_max_attempts`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from v17.smc_sb.config import INSTRUMENT_INDEX, StrategyConfig, variant_index
from v17.smc_sb.data import Market
from v17.smc_sb.execution import find_fill, run_exit
from v17.smc_sb.risk import r_unit, realized_r
from v17.smc_sb.session import NS_PER_MIN, ny_ns


class ControlExhaustedError(RuntimeError):
    """A control trade found no fill within the allowed redraws (test aborted, never padded)."""


@dataclass(frozen=True)
class ControlDay:
    w0_ns: int
    expiry_ns: int
    close_ns: int


def eligible_days(mk: Market, days: list[dt.date], cfg: StrategyConfig) -> list[ControlDay]:
    """XNYS, not early-close, not excluded, complete M1 in [data_check_start, order_expiry)."""
    out = []
    for d in days:
        if d not in mk.xnys or d in mk.early_close or d in mk.excluded_sessions:
            continue
        a, b = ny_ns(d, cfg.data_check_start), ny_ns(d, cfg.order_expiry)
        if mk.idx(b) - mk.idx(a) == (b - a) // NS_PER_MIN:
            out.append(ControlDay(ny_ns(d, cfg.window_start), b, ny_ns(d, cfg.force_close)))
    return out


def seed_for(instrument: str, cfg: StrategyConfig) -> int:
    return cfg.null_seed_base + 10 * INSTRUMENT_INDEX[instrument] + variant_index(cfg)


def control_trade_r(
    mk: Market,
    cd: ControlDay,
    side: int,
    minute: int,
    offset: float,
    stop_d: float,
    target_d: float,
    cfg: StrategyConfig,
) -> float | None:
    """One control trade on day `cd`; None if the limit does not fill before expiry."""
    placed = cd.w0_ns + minute * NS_PER_MIN
    jp = mk.idx(placed) - 1
    if jp < 0:
        return None
    ref = float(mk.ask["c"][jp] if side == 1 else mk.bid["c"][jp])
    limit = ref - side * offset
    stop, target = limit - side * stop_d, limit + side * target_d
    fi = find_fill(mk, side, limit, placed, cd.expiry_ns)
    if fi < 0:
        return None
    ex = run_exit(mk, side, fi, stop, target, cd.close_ns, cfg.slippage)
    unit = r_unit(limit, stop, cfg.slippage, cfg.commission_pts)
    return realized_r(side, limit, ex.price, unit, cfg.commission_pts)


def trade_features(trades: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """side, placement minute after window start, limit offset L_j, stop distance S_j, target distance T_j."""
    w0 = np.array(
        [ny_ns(pd.Timestamp(d).date(), cfg.window_start) for d in trades.trading_date],
        dtype=np.int64,
    )
    side = trades.side.to_numpy(int)
    return pd.DataFrame(
        {
            "side": side,
            "minute": (trades.placed_ns.to_numpy(np.int64) - w0) // NS_PER_MIN,
            "offset": (trades.placement_px.to_numpy(float) - trades.limit.to_numpy(float)) * side,
            "stop_d": (trades.limit - trades.stop).abs().to_numpy(float),
            "target_d": (trades.target - trades.limit).abs().to_numpy(float),
        }
    )


def matched_control_test(
    mk: Market,
    trades: pd.DataFrame,
    days: list[dt.date],
    cfg: StrategyConfig,
    *,
    perms: int | None = None,
    seed: int | None = None,
) -> dict[str, float]:
    perms = cfg.null_perms if perms is None else perms
    seed = seed_for(mk.instrument, cfg) if seed is None else seed
    pool = eligible_days(mk, days, cfg)
    if trades.empty or not pool:
        return {"p_one_sided": float("nan"), "perms": 0}
    f = trade_features(trades, cfg)
    real = float(trades.r.mean())
    sides, minutes = f.side.to_numpy(int), f.minute.to_numpy(np.int64)
    offsets, stop_ds, target_ds = (f[c].to_numpy(float) for c in ("offset", "stop_d", "target_d"))
    rng = np.random.default_rng(seed)
    null = np.empty(perms)
    attempts = fills = 0
    for p in range(perms):
        rs = np.empty(len(f))
        for k in range(len(f)):
            for _ in range(cfg.null_max_attempts):
                attempts += 1
                r = control_trade_r(
                    mk,
                    pool[int(rng.integers(0, len(pool)))],
                    int(sides[k]),
                    int(minutes[k]),
                    float(offsets[k]),
                    float(stop_ds[k]),
                    float(target_ds[k]),
                    cfg,
                )
                if r is not None:
                    fills += 1
                    rs[k] = r
                    break
            else:
                raise ControlExhaustedError(
                    f"perm {p} trade {k}: no fill in {cfg.null_max_attempts} draws"
                )
        null[p] = rs.mean()
    return {
        "real_mean_r": real,
        "null_mean_r_median": float(np.median(null)),
        "p_one_sided": float((1 + (null >= real).sum()) / (perms + 1)),
        "perms": perms,
        "seed": seed,
        "control_fill_rate": fills / attempts,
    }
