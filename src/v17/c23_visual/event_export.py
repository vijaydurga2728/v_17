"""Read-only adapter: frozen c21 `Engine` day events -> cycle 23 `VisualEvent` ledger + `DayRecord` (spec §4).

The engine is called exactly as the baseline calls it; its output objects are only read.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from v17.c23_visual.models import DayRecord, Scalar, Timeframe, VisualEvent
from v17.smc_sb.config import CONFIG_VERSION, StrategyConfig
from v17.smc_sb.data import Market
from v17.smc_sb.engine import DayResult, Engine
from v17.smc_sb.session import NS_PER_MIN, ny_ns

TIMEFRAME: dict[str, Timeframe] = {
    "bias": "D1",
    "levels": "D1",
    "asia_missing": "D1",
    "mss": "15m",
    "order_filled": "1m",
    "exit": "1m",
    "order_expired_cancelled": "1m",
}  # everything else is a 5 m stage
PRICE_KEY = {
    "sweep": "extreme",
    "mss": "close",
    "fvg": "top",
    "order_created": "limit",
    "order_filled": "price",
    "exit": "price",
}
WINDOW_END_REASONS = frozenset({"no_sweep", "no_mss", "no_fvg_after_mss"})
EXCLUDED_REASONS = frozenset(
    {
        "not_xnys_session",
        "excluded_session_bad_quotes",
        "early_close_day",
        "missing_m1",
        "no_daily_session",
        "no_previous_day",
    }
)


def data_fingerprint(mk: Market) -> str:
    h = hashlib.sha256(np.ascontiguousarray(mk.ts).tobytes())
    for side in (mk.bid, mk.ask):
        for f in ("o", "h", "l", "c"):
            h.update(np.ascontiguousarray(side[f]).tobytes())
    return h.hexdigest()[:16]


def _scalar(v: object) -> Scalar:
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(float(v)) else float(v)
    if isinstance(v, (np.integer, int)) and not isinstance(v, bool):
        return int(v)
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return None if v is None else str(v)


def _ns(iso: object) -> int | None:
    return int(pd.Timestamp(str(iso)).value) if iso else None


def _utc(ns: int) -> dt.datetime:
    return pd.Timestamp(ns, tz="UTC").to_pydatetime()


@dataclass(frozen=True)
class ExportContext:
    mk: Market
    cfg: StrategyConfig
    data_fp: str


def _available(
    stage: str, t: int | None, prev: int, reason: str | None, day: dt.date, cfg: StrategyConfig
) -> int:
    """Earliest moment the engine could legitimately know this event (spec §4)."""
    if stage == "sweep" and t is not None:
        return t + cfg.fvg_tf_min * NS_PER_MIN  # 5 m sweep candle close
    if stage in ("order_filled", "exit") and t is not None:
        return t + NS_PER_MIN  # M1 bar close
    if t is not None:
        return max(t, prev)  # mss / fvg / order times are already candle closes
    if stage == "rejected" and reason in WINDOW_END_REASONS:
        return max(prev, ny_ns(day, cfg.window_end))
    if stage == "rejected" and reason == "unfilled_expired":
        return max(prev, ny_ns(day, cfg.order_expiry))
    return prev


def day_events(ctx: ExportContext, res: DayResult) -> list[VisualEvent]:
    mk, cfg, day = ctx.mk, ctx.cfg, res.day
    prev = ny_ns(day, cfg.window_start)
    out: list[VisualEvent] = []
    for seq, e in enumerate(res.events):
        stage = str(e["stage"])
        t = _ns(e.get("ts"))
        reason = str(e["reason"]) if stage == "rejected" else None
        avail = _available(stage, t, prev, reason, day, cfg)
        prev = avail
        payload = {k: _scalar(v) for k, v in e.items() if k not in ("day", "stage", "ts")}
        pk = PRICE_KEY.get(stage)
        price = payload.get(pk) if pk else None
        status = "invalidated" if stage in ("rejected", "order_expired_cancelled") else "confirmed"
        out.append(
            VisualEvent(
                event_id=f"{mk.instrument}_{day.isoformat()}_{seq:03d}_{stage}",
                instrument=mk.instrument,
                trading_date=day.isoformat(),
                seq=seq,
                stage=stage,
                event_time=_utc(t) if t is not None else None,
                available_at=_utc(avail),
                timeframe=TIMEFRAME.get(stage, "5m"),
                price=float(price)
                if isinstance(price, (int, float)) and not isinstance(price, bool)
                else None,
                rule_id=f"c21.{stage}",
                confirmation_status=status,
                rejection_reason=reason,
                source_bar_ns=t,
                payload=payload,
                data_fingerprint=ctx.data_fp,
                config_fingerprint=cfg.fingerprint(),
                engine_version=CONFIG_VERSION,
            )
        )
    return out


def classify(res: DayResult, events: list[VisualEvent], cfg: StrategyConfig) -> DayRecord:
    stages = {e.stage for e in events}
    swept = "sweep" in stages
    if res.reason == "trade":
        cat = "filled"
    elif res.reason == "unfilled_expired":
        cat = "unfilled_expired"
    elif res.reason in EXCLUDED_REASONS:
        cat = "excluded"
    elif swept:
        cat = "rejected_after_sweep"
    else:
        cat = "rejected_pre_sweep"
    near = res.reason if swept and "mss" in stages and cat == "rejected_after_sweep" else None
    cut = end = None
    if swept:
        orders = [e for e in events if e.stage == "order_created"]
        rej = [e for e in events if e.stage == "rejected"]
        cut_ev = orders[-1] if orders else rej[-1]
        cut = int(pd.Timestamp(cut_ev.available_at).value)
        exits = [e for e in events if e.stage == "exit"]
        close = ny_ns(res.day, cfg.force_close)
        end = int(pd.Timestamp(exits[-1].available_at).value) if exits else close
    return DayRecord(
        instrument=events[0].instrument if events else "",
        trading_date=res.day.isoformat(),
        result=res.reason,
        category=cat,
        charted=swept,
        near_miss_stage=near,
        cut_ns=cut,
        end_ns=end,
        event_ids=tuple(e.event_id for e in events),
    )


def export(
    mk: Market, cfg: StrategyConfig, days: Iterable[dt.date]
) -> tuple[list[DayRecord], list[VisualEvent], list[DayResult]]:
    """Run the frozen engine day by day (as `Engine.run` does) and convert its log. Returns raw results too so callers
    can prove the baseline output is unchanged (gate 1)."""
    eng = Engine(mk, cfg)
    ctx = ExportContext(mk, cfg, data_fingerprint(mk))
    records: list[DayRecord] = []
    ledger: list[VisualEvent] = []
    raw: list[DayResult] = []
    for d in days:
        res = eng.run_day(d)
        evs = day_events(ctx, res)
        records.append(classify(res, evs, cfg))
        ledger.extend(evs)
        raw.append(res)
    return records, ledger, raw
