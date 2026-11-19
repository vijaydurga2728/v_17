"""Pure-data ICT annotations built from the ledger (spec §5). No drawing here, so coordinates are testable exactly."""

from __future__ import annotations

import hashlib
import json
import math

import pandas as pd

from v17.c23_visual.models import Annotation, DayRecord, VisualEvent
from v17.smc_sb.config import StrategyConfig
from v17.smc_sb.session import NS_PER_MIN, ny_ns

DAY_NS = 24 * 60 * NS_PER_MIN


def _ns(x: object) -> int:
    return int(pd.Timestamp(x).value)  # type: ignore[arg-type]


def _f(e: VisualEvent, k: str) -> float:
    v = e.payload.get(k)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else float("nan")


def build(rec: DayRecord, events: list[VisualEvent], cfg: StrategyConfig) -> list[Annotation]:  # noqa: PLR0912, PLR0915
    """All annotations for one charted day, each tagged with when it became knowable."""
    day = pd.Timestamp(rec.trading_date).date()
    t_day0 = ny_ns(day, "00:00")
    d_lo, d_hi = t_day0 - 40 * DAY_NS, t_day0 + DAY_NS
    t_exp, t_close = ny_ns(day, cfg.order_expiry), ny_ns(day, cfg.force_close)
    out: list[Annotation] = []

    def add(**kw: object) -> None:
        out.append(Annotation.model_validate(kw))

    for e in events:
        av = _ns(e.available_at)
        t = _ns(e.event_time) if e.event_time is not None else None
        eid = e.event_id
        if e.stage == "levels":
            for name in ("pdh", "pdl"):
                p = _f(e, name)
                if not math.isnan(p):
                    add(
                        panel="D1",
                        kind="hline",
                        label=name.upper(),
                        t0=d_lo,
                        t1=d_hi,
                        p0=p,
                        p1=p,
                        available_ns=av,
                        event_id=eid,
                    )
                    add(
                        panel="15m",
                        kind="hline",
                        label=name.upper(),
                        t0=t_day0,
                        t1=t_close,
                        p0=p,
                        p1=p,
                        available_ns=av,
                        event_id=eid,
                    )
            for name, lab in (("asia_h", "ASIA H"), ("asia_l", "ASIA L")):
                p = _f(e, name)
                if not math.isnan(p):
                    add(
                        panel="15m",
                        kind="hline",
                        label=lab,
                        t0=t_day0,
                        t1=t_close,
                        p0=p,
                        p1=p,
                        available_ns=av,
                        event_id=eid,
                    )
        elif e.stage == "bias":
            for name, lab in (("last_high", "swing H"), ("last_low", "swing L")):
                p = _f(e, name)
                if not math.isnan(p):
                    add(
                        panel="D1",
                        kind="hline",
                        label=f"{lab} ({e.payload.get('rule')})",
                        t0=d_lo,
                        t1=d_hi,
                        p0=p,
                        p1=p,
                        available_ns=av,
                        event_id=eid,
                    )
        elif e.stage == "premium_discount":
            p = _f(e, "equilibrium")
            if not math.isnan(p):
                add(
                    panel="D1",
                    kind="hline",
                    label=f"EQ ({e.payload.get('state')})",
                    t0=d_lo,
                    t1=d_hi,
                    p0=p,
                    p1=p,
                    available_ns=av,
                    event_id=eid,
                )
        elif e.stage == "sweep" and t is not None:
            ref = _f(e, "ref_price")
            add(
                panel="15m",
                kind="hline",
                label=f"swept {e.payload.get('ref')}",
                t0=t_day0,
                t1=t_close,
                p0=ref,
                p1=ref,
                available_ns=av,
                event_id=eid,
            )
            add(
                panel="5m",
                kind="marker",
                label="sweep",
                t0=t,
                t1=t,
                p0=_f(e, "extreme"),
                p1=_f(e, "extreme"),
                available_ns=av,
                event_id=eid,
            )
            add(
                panel="15m",
                kind="marker",
                label="sweep",
                t0=t,
                t1=t,
                p0=_f(e, "extreme"),
                p1=_f(e, "extreme"),
                available_ns=av,
                event_id=eid,
            )
        elif e.stage == "mss" and t is not None:
            sw = _ns(str(e.payload["swing_ts"]))
            p = _f(e, "broken_swing")
            add(
                panel="15m",
                kind="hline",
                label="MSS level",
                t0=sw,
                t1=t,
                p0=p,
                p1=p,
                available_ns=av,
                event_id=eid,
            )
            add(
                panel="15m",
                kind="marker",
                label="MSS close",
                t0=t - cfg.mss_tf_min * NS_PER_MIN,
                t1=t,
                p0=_f(e, "close"),
                p1=_f(e, "close"),
                available_ns=av,
                event_id=eid,
            )
        elif e.stage == "fvg" and t is not None:
            disp = _ns(str(e.payload["displacement_ts"]))
            w = cfg.fvg_tf_min * NS_PER_MIN
            add(
                panel="5m",
                kind="box",
                label="FVG",
                t0=disp - w,
                t1=t_exp,
                p0=_f(e, "bottom"),
                p1=_f(e, "top"),
                available_ns=av,
                event_id=eid,
            )
            add(
                panel="5m",
                kind="vspan",
                label="displacement",
                t0=disp,
                t1=disp + w,
                p0=0.0,
                p1=0.0,
                available_ns=av,
                event_id=eid,
            )
        elif e.stage == "ote":
            lo, hi = _f(e, "zone_lo"), _f(e, "zone_hi")
            if not (math.isnan(lo) or math.isnan(hi)):
                add(
                    panel="5m",
                    kind="box",
                    label="OTE",
                    t0=ny_ns(day, cfg.window_start),
                    t1=t_exp,
                    p0=lo,
                    p1=hi,
                    available_ns=av,
                    event_id=eid,
                )
        elif e.stage == "order_created" and t is not None:
            for k, lab in (
                ("limit", "limit"),
                ("stop", "stop"),
                ("target", f"target {e.payload.get('target_name')}"),
            ):
                p = _f(e, k)
                for panel in ("5m", "1m"):
                    add(
                        panel=panel,
                        kind="hline",
                        label=lab,
                        t0=t,
                        t1=t_exp,
                        p0=p,
                        p1=p,
                        available_ns=av,
                        event_id=eid,
                    )
        elif e.stage == "order_filled" and t is not None:
            p = _f(e, "price")
            add(
                panel="1m",
                kind="marker",
                label="fill",
                t0=t,
                t1=t,
                p0=p,
                p1=p,
                available_ns=av,
                event_id=eid,
                outcome_only=True,
            )
        elif e.stage == "exit" and t is not None:
            p = _f(e, "price")
            lab = f"exit {e.payload.get('reason')} R={_f(e, 'r'):.2f}"
            add(
                panel="1m",
                kind="marker",
                label=lab,
                t0=t,
                t1=t,
                p0=p,
                p1=p,
                available_ns=av,
                event_id=eid,
                outcome_only=True,
            )
    return out


def decision_view(annos: list[Annotation], cut_ns: int) -> list[Annotation]:
    """Spec §5: only what was knowable at the cut; boxes/lines clipped so nothing extends past it."""
    keep = []
    for a in annos:
        if a.outcome_only or a.available_ns > cut_ns:
            continue
        keep.append(
            a.model_copy(update={"t1": min(a.t1, cut_ns)}) if a.kind in ("hline", "box") else a
        )
    return keep


def fingerprint(annos: list[Annotation]) -> str:
    blob = json.dumps([a.model_dump() for a in annos], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
