"""Deterministic M1 bid/ask fills and exits (spec §11-12, D8, D10, R13-R16)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from v17.smc_sb.data import Market
from v17.smc_sb.session import NS_PER_MIN

STOP, TARGET, FORCED = "stop", "target", "force_close_16"


def find_fill(mk: Market, side: int, limit: float, placed_ns: int, expiry_ns: int) -> int:
    """R13: first M1 bar starting in [placed_ns, expiry_ns) where the limit trades; -1 if none.

    Long fills when ask_low <= limit, short when bid_high >= limit; fill price is always the limit.
    """
    i, j = mk.idx(placed_ns), mk.idx(expiry_ns)
    if j <= i:
        return -1
    hit = mk.ask["l"][i:j] <= limit if side == 1 else mk.bid["h"][i:j] >= limit
    k = np.flatnonzero(hit)
    return i + int(k[0]) if len(k) else -1


@dataclass(frozen=True)
class Exit:
    idx: int
    reason: str
    price: float
    data_gap: bool


def run_exit(
    mk: Market, side: int, fill_i: int, stop: float, target: float, close_ns: int, slippage: float
) -> Exit:
    """R15/R16: stop first on every bar from the fill bar; target from the bar after the fill bar;
    otherwise force close on the M1 bar ending at `close_ns` (bid close long / ask close short) with slippage."""
    jc = mk.idx(close_ns) - 1
    gap = jc < 0 or int(mk.ts[jc]) != close_ns - NS_PER_MIN
    jc = max(jc, fill_i)
    if side == 1:
        s_hit = mk.bid["l"][fill_i : jc + 1] <= stop
        t_hit = mk.bid["h"][fill_i : jc + 1] >= target
    else:
        s_hit = mk.ask["h"][fill_i : jc + 1] >= stop
        t_hit = mk.ask["l"][fill_i : jc + 1] <= target
    t_hit[0] = False
    s = np.flatnonzero(s_hit)
    t = np.flatnonzero(t_hit)
    if len(s) and (not len(t) or s[0] <= t[0]):
        return Exit(fill_i + int(s[0]), STOP, stop - side * slippage, False)
    if len(t):
        return Exit(fill_i + int(t[0]), TARGET, target, False)
    px = mk.bid["c"][jc] if side == 1 else mk.ask["c"][jc]
    return Exit(jc, FORCED, float(px) - side * slippage, gap)
