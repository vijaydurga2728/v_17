"""Frozen descriptive metrics (spec §6), computed from raw 5 m mid candles only, never from the engine's detectors.

REPORT-ONLY. Cycle 23 must not use any of these to filter or select trades (spec D8, D11).

Definitions (frozen 2026-11-19, before any real data):
- ATR14(k): mean true range of the 14 completed 5 m candles before candle k (TR uses the previous candle's close);
  NaN if fewer than 15 candles exist before k.
- disp_body_ratio: |close - open| / (high - low) of the displacement candle (FVG candle 2).
- disp_range_atr: (high - low) of the displacement candle / ATR14 at that candle.
- fvg_size_atr: (top - bottom) / ATR14 at the displacement candle.
- sweep_depth: |sweep candle extreme - swept reference price| in points.
- sweep_close_inside: the sweep candle's close is strictly back on the inside of the reference.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from v17.c23_visual.models import VisualEvent
from v17.smc_sb.data import Market

METRICS_VERSION = "23.m1"
ATR_N = 14


@dataclass(frozen=True)
class CandidateMetrics:
    sweep_depth: float = math.nan
    sweep_close_inside: bool | None = None
    disp_body_ratio: float = math.nan
    disp_range_atr: float = math.nan
    fvg_size_atr: float = math.nan

    def as_dict(self) -> dict[str, float | bool | None]:
        return asdict(self)


def atr14(c5: pd.DataFrame, k: int) -> float:
    if k < ATR_N + 1:
        return math.nan
    h, lo, c = (c5[x].to_numpy(float)[k - ATR_N - 1 : k] for x in ("h", "l", "c"))
    prev_c = c[:-1]
    tr = np.maximum.reduce([h[1:] - lo[1:], np.abs(h[1:] - prev_c), np.abs(lo[1:] - prev_c)])
    return float(tr.mean())


def _num(v: object) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else math.nan


def candidate_metrics(mk: Market, events: list[VisualEvent]) -> CandidateMetrics:
    """Metrics for the LAST sweep / FVG of the day (the setup that produced the order or the final rejection)."""
    c5 = mk.c5
    starts = c5.start.to_numpy()
    out: dict[str, float | bool | None] = {}
    sweeps = [e for e in events if e.stage == "sweep" and e.source_bar_ns is not None]
    if sweeps:
        s = sweeps[-1]
        assert s.source_bar_ns is not None
        ref, ext = _num(s.payload.get("ref_price")), _num(s.payload.get("extreme"))
        out["sweep_depth"] = abs(ext - ref)
        k = int(np.searchsorted(starts, s.source_bar_ns))
        if k < len(starts) and starts[k] == s.source_bar_ns:
            close = float(c5.c.to_numpy()[k])
            long_side = ext < ref
            out["sweep_close_inside"] = close > ref if long_side else close < ref
    fvgs = [e for e in events if e.stage == "fvg"]
    if fvgs:
        f = fvgs[-1]
        disp_ns = int(pd.Timestamp(str(f.payload["displacement_ts"])).value)
        k = int(np.searchsorted(starts, disp_ns))
        if k < len(starts) and starts[k] == disp_ns:
            o, h, lo, c = (float(c5[x].to_numpy()[k]) for x in ("o", "h", "l", "c"))
            rng = h - lo
            a = atr14(c5, k)
            out["disp_body_ratio"] = abs(c - o) / rng if rng > 0 else math.nan
            out["disp_range_atr"] = rng / a if a > 0 else math.nan
            size = _num(f.payload.get("top")) - _num(f.payload.get("bottom"))
            out["fvg_size_atr"] = size / a if a > 0 else math.nan
    return CandidateMetrics(**out)  # type: ignore[arg-type]
