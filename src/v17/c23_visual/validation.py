"""Gate checks for cycle 23 (spec §7). Each returns a list of violation strings; empty = pass."""

from __future__ import annotations

import pandas as pd

from v17.c23_visual.chart_builder import panel_candles, view_annotations
from v17.c23_visual.models import Annotation, DayRecord, VisualEvent
from v17.smc_sb.config import StrategyConfig
from v17.smc_sb.data import Market
from v17.smc_sb.session import NS_PER_MIN

# where an event's source time must exist: (frame attribute, column)
SOURCE = {
    "sweep": ("c5", "start"),
    "mss": ("c15", "end"),
    "fvg": ("c5", "end"),
    "order_created": ("c5", "end"),
    "order_filled": ("m1", "start"),
    "exit": ("m1", "start"),
}


def ledger_violations(mk: Market, ledger: list[VisualEvent], cfg: StrategyConfig) -> list[str]:
    """Gate 2 + the timing half of gate 3."""
    bad: list[str] = []
    ids = [e.event_id for e in ledger]
    if len(ids) != len(set(ids)):
        bad.append("duplicate event_id")
    for e in ledger:
        if e.stage == "rejected" and not e.rejection_reason:
            bad.append(f"{e.event_id}: rejection without reason")
        if e.event_time is not None and pd.Timestamp(e.available_at) < pd.Timestamp(e.event_time):
            bad.append(f"{e.event_id}: available_at before event_time")
        src = SOURCE.get(e.stage)
        if src and e.source_bar_ns is not None:
            frame, col = src
            arr = mk.ts if frame == "m1" else getattr(mk, frame)[col].to_numpy()
            if e.source_bar_ns not in set(arr.tolist()):
                bad.append(f"{e.event_id}: no source bar at {e.source_bar_ns}")
        if e.stage == "mss":
            swing = int(pd.Timestamp(str(e.payload["swing_ts"])).value)
            confirmed = swing + (cfg.mss_pivot_right + 1) * cfg.mss_tf_min * NS_PER_MIN
            if confirmed > int(pd.Timestamp(e.available_at).value):
                bad.append(f"{e.event_id}: broken swing not confirmed before MSS")
        if e.stage == "fvg":
            c3_close = e.source_bar_ns
            if c3_close is None or int(pd.Timestamp(e.available_at).value) < c3_close:
                bad.append(f"{e.event_id}: FVG visible before candle 3 closes")
    return bad


def decision_violations(mk: Market, rec: DayRecord, annos: list[Annotation]) -> list[str]:
    """Gate 3: decision view has no candle closing after the cut and no annotation knowable after it."""
    assert rec.cut_ns is not None
    bad: list[str] = []
    for p, c in panel_candles(mk, rec, "decision").items():
        if len(c.end) and int(c.end.max()) > rec.cut_ns:
            bad.append(f"{rec.trading_date} {p}: candle closes after cut")
    for a in view_annotations(annos, rec, "decision"):
        if a.outcome_only:
            bad.append(f"{a.event_id}: outcome annotation in decision view")
        if a.available_ns > rec.cut_ns:
            bad.append(f"{a.event_id}: annotation available after cut")
        if a.kind in ("hline", "box") and a.t1 > rec.cut_ns:
            bad.append(f"{a.event_id}: annotation extends past cut")
    return bad
