"""R24 matched random-entry null: same instrument, direction, trade count, session window, stop/target
distances and exit rules as the real trades; random date and random entry minute in [10:00, 11:05)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from v17.smc_sb.config import StrategyConfig
from v17.smc_sb.data import Market
from v17.smc_sb.execution import run_exit
from v17.smc_sb.risk import r_unit, realized_r
from v17.smc_sb.session import NS_PER_MIN, ny_ns


def eligible_days(mk: Market, days: list[dt.date], cfg: StrategyConfig) -> list[tuple[int, int]]:
    """(first entry-bar index, force-close ns) for days with every M1 bar in [window start, expiry)."""
    out = []
    for d in days:
        a, b = ny_ns(d, cfg.window_start), ny_ns(d, cfg.order_expiry)
        i, j = mk.idx(a), mk.idx(b)
        if j - i == (b - a) // NS_PER_MIN:
            out.append((i, ny_ns(d, cfg.force_close)))
    return out


def random_trade_r(
    mk: Market,
    side: int,
    bar: int,
    close_ns: int,
    stop_d: float,
    target_d: float,
    cfg: StrategyConfig,
) -> float:
    entry = float(mk.ask["o"][bar] if side == 1 else mk.bid["o"][bar])
    stop, target = entry - side * stop_d, entry + side * target_d
    ex = run_exit(mk, side, bar, stop, target, close_ns, cfg.slippage)
    return realized_r(
        side,
        entry,
        ex.price,
        r_unit(entry, stop, cfg.slippage, cfg.commission_pts),
        cfg.commission_pts,
    )


def matched_random_test(
    mk: Market,
    trades: pd.DataFrame,
    days: list[dt.date],
    cfg: StrategyConfig,
    seed: int,
    perms: int | None = None,
) -> dict[str, float]:
    perms = cfg.null_perms if perms is None else perms
    pool = eligible_days(mk, days, cfg)
    if trades.empty or not pool:
        return {"p_mean_r": float("nan"), "null_median": float("nan"), "perms": 0}
    minutes = (
        ny_ns(dt.date(2024, 1, 2), cfg.order_expiry) - ny_ns(dt.date(2024, 1, 2), cfg.window_start)
    ) // NS_PER_MIN
    side = trades.side.to_numpy(int)
    stop_d = (trades.limit - trades.stop).abs().to_numpy(float)
    tgt_d = (trades.target - trades.limit).abs().to_numpy(float)
    real = float(trades.r.mean())
    rng = np.random.default_rng(seed)
    null = np.empty(perms)
    for p in range(perms):
        di = rng.integers(0, len(pool), size=len(side))
        mi = rng.integers(0, minutes, size=len(side))
        rs = [
            random_trade_r(
                mk,
                int(side[k]),
                pool[di[k]][0] + int(mi[k]),
                pool[di[k]][1],
                stop_d[k],
                tgt_d[k],
                cfg,
            )
            for k in range(len(side))
        ]
        null[p] = float(np.mean(rs))
    return {
        "p_mean_r": float((1 + (null >= real).sum()) / (perms + 1)),
        "null_median": float(np.median(null)),
        "real_mean_r": real,
        "perms": perms,
    }
