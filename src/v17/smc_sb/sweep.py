"""D2 / R5 (corrected): liquidity sweep = first breach of an unconsumed reference, on a completed 5-minute
candle inside the window that closes strictly back inside."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from v17.smc_sb.data import Market
from v17.smc_sb.session import NS_PER_MIN


@dataclass(frozen=True)
class Ref:
    name: str  # "PDL", "PDH", "ASIA_LOW", "ASIA_HIGH"
    price: float
    created_ns: int


@dataclass(frozen=True)
class Sweep:
    idx: int  # position in the 5 m candle frame
    start_ns: int
    end_ns: int
    ref_name: str
    ref_price: float
    ref_created_ns: int
    extreme: float  # candle low (long) / high (short)


def first_breach_ns(mk: Market, side: int, ref: Ref, until_ns: int) -> int:
    """Start time of the first M1 bar after creation whose mid trades strictly beyond the ref; -1 if none."""
    i, j = mk.idx(ref.created_ns), mk.idx(until_ns)
    if j <= i:
        return -1
    hit = mk.mid["l"][i:j] < ref.price if side == 1 else mk.mid["h"][i:j] > ref.price
    k = np.flatnonzero(hit)
    return int(mk.ts[i + int(k[0])]) if len(k) else -1


def find_sweep(
    mk: Market,
    side: int,
    refs: list[Ref],
    win_start_ns: int,
    win_end_ns: int,
    not_before_ns: int,
    tf_min: int = 5,
) -> tuple[Sweep | None, list[dict[str, object]]]:
    """Earliest qualifying sweep across `refs` (tie: list order) plus a status record per ref.

    A ref qualifies only if its first breach since creation falls in a 5 m candle that starts at or after
    `not_before_ns` (and the window start), ends by the window end, and closes strictly back inside.
    """
    width = tf_min * NS_PER_MIN
    c5 = mk.c5
    starts, ends = c5.start.to_numpy(), c5.end.to_numpy()
    lows, highs, closes = c5.l.to_numpy(float), c5.h.to_numpy(float), c5.c.to_numpy(float)
    best: Sweep | None = None
    status: list[dict[str, object]] = []
    for ref in refs:
        t = first_breach_ns(mk, side, ref, win_end_ns)
        if t < 0:
            status.append({"ref": ref.name, "status": "not_breached"})
            continue
        cs = t - t % width
        if cs < win_start_ns:
            status.append({"ref": ref.name, "status": "consumed_before_window", "breach_ns": t})
            continue
        if cs < not_before_ns:
            status.append({"ref": ref.name, "status": "consumed_by_earlier_setup", "breach_ns": t})
            continue
        k = int(np.searchsorted(starts, cs))
        if k >= len(starts) or int(starts[k]) != cs or int(ends[k]) > win_end_ns:
            status.append({"ref": ref.name, "status": "breach_candle_missing", "breach_ns": t})
            continue
        close = float(closes[k])
        back_inside = close > ref.price if side == 1 else close < ref.price
        if not back_inside:
            status.append({"ref": ref.name, "status": "breached_no_close_back", "breach_ns": t})
            continue
        ext = float(lows[k] if side == 1 else highs[k])
        status.append({"ref": ref.name, "status": "sweep", "breach_ns": t})
        cand = Sweep(k, cs, cs + width, ref.name, ref.price, ref.created_ns, ext)
        if best is None or cand.start_ns < best.start_ns:
            best = cand
    return best, status
