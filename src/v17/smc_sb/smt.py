"""D11 / R25: SMT divergence (separate experiment only; disabled in the baseline)."""

from __future__ import annotations

import math

import numpy as np

from v17.smc_sb.data import Market


def smt_divergence(
    primary: Market,
    partner: Market,
    side: int,
    partner_ref: float,
    win_start_ns: int,
    sweep_end_ns: int,
) -> tuple[bool | None, str]:
    """True if the partner fails to break its same-named reference while the primary sweeps.

    Uses the partner's 5 m candles from window start up to the primary sweep candle close; every primary candle
    in that span must have a partner candle with the identical start (max timestamp difference 0).
    Returns (None, reason) when data is missing.
    """
    if math.isnan(partner_ref):
        return None, "smt_partner_ref_missing"
    p, q = primary.c5, partner.c5
    ps = p.start.to_numpy()[
        (p.start.to_numpy() >= win_start_ns) & (p.end.to_numpy() <= sweep_end_ns)
    ]
    qmask = (q.start.to_numpy() >= win_start_ns) & (q.end.to_numpy() <= sweep_end_ns)
    if len(ps) == 0 or not np.array_equal(ps, q.start.to_numpy()[qmask]):
        return None, "smt_unsynchronized"
    if side == 1:
        held = bool(q.l.to_numpy()[qmask].min() > partner_ref)
    else:
        held = bool(q.h.to_numpy()[qmask].max() < partner_ref)
    return held, "smt_divergence" if held else "smt_no_divergence"
