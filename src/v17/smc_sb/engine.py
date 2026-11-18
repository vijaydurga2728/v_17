"""Cycle 21 per-day pipeline: every stage records an event; every rejection records its reason (spec §12).

Spec v1.2 (review 1): R5 first-breach sweeps, R9 continued MSS scan, R12 re-scan after an expired order,
R15 gap-through stops, R27 excluded sessions, R28 early-close days, R29 XNYS-only daily table, R30 flags.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from v17.smc_sb.config import StrategyConfig
from v17.smc_sb.data import Market
from v17.smc_sb.entry_models import Order, model_a, model_b_ok
from v17.smc_sb.execution import find_fill, run_exit
from v17.smc_sb.fvg import FVG, find_fvg
from v17.smc_sb.liquidity import DayLevels, Target, day_levels, select_target
from v17.smc_sb.market_bias import Bias, DailyStructure
from v17.smc_sb.premium_discount import eligible, equilibrium, zone
from v17.smc_sb.risk import realized_r
from v17.smc_sb.session import NS_PER_MIN, ny_ns
from v17.smc_sb.smt import smt_divergence
from v17.smc_sb.structure import MSS, find_mss, pivot_flags
from v17.smc_sb.sweep import Ref, Sweep, find_sweep

SESSION = "NY_AM_10_11"
Event = dict[str, object]


def _iso(ns: int) -> str:
    return pd.Timestamp(ns, tz="UTC").tz_convert("America/New_York").isoformat()


@dataclass
class DayResult:
    day: dt.date
    reason: str  # "trade" or a rejection reason
    events: list[Event] = field(default_factory=list)
    trade: dict[str, object] | None = None


@dataclass(frozen=True)
class Setup:
    sweep: Sweep
    mss: MSS
    fvg: FVG
    order: Order
    target: Target
    eq: float
    pd_state: str
    smt_status: str
    ote: tuple[float, float]


class Engine:
    def __init__(self, mk: Market, cfg: StrategyConfig, partner: Market | None = None) -> None:
        if cfg.smt_enabled and partner is None:
            raise ValueError("SMT experiment requires a partner market")
        self.mk, self.cfg, self.partner = mk, cfg, partner
        self.ds = DailyStructure(mk.daily, cfg.daily_pivot_left, cfg.daily_pivot_right)
        self.ph15, self.pl15 = pivot_flags(
            mk.c15.h.to_numpy(), mk.c15.l.to_numpy(), cfg.mss_pivot_left, cfg.mss_pivot_right
        )

    # ------------------------------------------------------------------ one setup chain
    def _setup(
        self,
        day: dt.date,
        side: int,
        bias: Bias,
        lv: DayLevels,
        refs: list[Ref],
        not_before: int,
        ev: list[Event],
    ) -> tuple[Setup | None, str]:
        mk, cfg = self.mk, self.cfg
        w0, w1 = ny_ns(day, cfg.window_start), ny_ns(day, cfg.window_end)

        def log(stage: str, ns: int | None = None, /, **d: object) -> None:
            ev.append({"day": day.isoformat(), "stage": stage, "ts": _iso(ns) if ns else "", **d})

        sw, statuses = find_sweep(mk, side, refs, w0, w1, not_before, cfg.fvg_tf_min)
        log("sweep_scan", not_before=_iso(not_before), refs=str(statuses))
        if sw is None:
            return None, "no_sweep"
        log("sweep", sw.start_ns, ref=sw.ref_name, ref_price=sw.ref_price, extreme=sw.extreme)
        smt_status = "disabled"
        if cfg.smt_enabled:
            assert self.partner is not None
            p = self.partner
            ppos = p.day_pos(pd.Timestamp(day))
            if ppos <= 0:
                return None, "smt_partner_missing"
            plv = day_levels(p, day, ppos, cfg.daily_rollover_hour)
            pref = {
                "PDL": plv.pdl,
                "PDH": plv.pdh,
                "ASIA_LOW": plv.asia_l,
                "ASIA_HIGH": plv.asia_h,
            }[sw.ref_name]
            ok, smt_status = smt_divergence(mk, p, side, pref, w0, sw.end_ns)
            log("smt", partner=p.instrument, partner_ref=pref, result=smt_status)
            if not ok:
                return None, smt_status
        mss, why = find_mss(
            mk.c15, self.ph15, self.pl15, side, sw.end_ns, w0, w1, cfg.mss_pivot_right
        )
        if mss is None:
            return None, why
        log(
            "mss",
            mss.end_ns,
            close=mss.close,
            broken_swing=mss.swing_price,
            swing_ts=_iso(int(mk.c15.start.to_numpy()[mss.swing_idx])),
        )
        fvg = find_fvg(mk.c5, side, mss.end_ns, w1, cfg.fvg_tf_min)
        if fvg is None:
            return None, "no_fvg_after_mss"
        log(
            "fvg",
            fvg.formed_ns,
            bottom=fvg.bottom,
            top=fvg.top,
            displacement_ts=_iso(fvg.c2_start_ns),
        )
        order = model_a(fvg, side)  # R12: limit = FVG proximal boundary
        ote = (math.nan, math.nan)
        if cfg.entry_model == "B":
            ia, ib = mk.idx(sw.start_ns), mk.idx(mss.end_ns)
            impulse = float(mk.mid["h"][ia:ib].max() if side == 1 else mk.mid["l"][ia:ib].min())
            ok_b, ote = model_b_ok(fvg, side, sw.extreme, impulse, cfg.ote_low, cfg.ote_high)
            log(
                "ote",
                zone_lo=ote[0],
                zone_hi=ote[1],
                impulse_extreme=impulse,
                proximal=fvg.proximal,
            )
            if not ok_b:
                return None, "ote_proximal_outside_zone"
        eq = equilibrium(bias)
        pd_state = zone(order.limit, eq)
        log("premium_discount", equilibrium=eq, state=pd_state)
        if math.isnan(eq):
            return None, "no_daily_swing_range"
        if not eligible(side, order.limit, eq):
            return None, "premium_discount_fail"
        ts_ = select_target(
            mk,
            lv,
            side,
            order.limit,
            order.stop,
            fvg.formed_ns,
            cfg.min_rr,
            cfg.slippage,
            cfg.commission_pts,
        )
        if ts_.contaminated:
            return None, "reference_window_contaminated"
        log("targets", candidates=str(ts_.candidates))
        if ts_.target is None:
            return None, "no_target_min_rr"
        return Setup(sw, mss, fvg, order, ts_.target, eq, pd_state, smt_status, ote), "ok"

    # ------------------------------------------------------------------ one trading date
    def run_day(self, day: dt.date) -> DayResult:  # noqa: PLR0912, PLR0915
        mk, cfg = self.mk, self.cfg
        res = DayResult(day, "")

        def ev(stage: str, ns: int | None = None, /, **d: object) -> None:
            res.events.append(
                {"day": day.isoformat(), "stage": stage, "ts": _iso(ns) if ns else "", **d}
            )

        def reject(reason: str, **d: object) -> DayResult:
            ev("rejected", reason=reason, **d)
            res.reason = reason
            return res

        if day not in mk.xnys:
            return reject("not_xnys_session")  # R29
        if day in mk.excluded_sessions:
            return reject(
                "excluded_session_bad_quotes", cause=mk.exclusion_reason.get(day, "")
            )  # R27/R31
        if day in mk.early_close:
            return reject("early_close_day")  # R28
        w1 = ny_ns(day, cfg.window_end)
        t_chk, t_exp = ny_ns(day, cfg.data_check_start), ny_ns(day, cfg.order_expiry)
        t_close = ny_ns(day, cfg.force_close)
        expected = (t_exp - t_chk) // NS_PER_MIN
        have = mk.idx(t_exp) - mk.idx(t_chk)
        if have != expected:  # R20
            return reject("missing_m1", expected=int(expected), have=int(have))
        i = mk.day_pos(pd.Timestamp(day))
        if i < 0:
            return reject("no_daily_session")
        if i == 0:
            return reject("no_previous_day")
        bias = self.ds.bias(i)
        ev(
            "bias",
            direction=bias.direction,
            rule=bias.reason,
            last_high=bias.last_high,
            prev_high=bias.prev_high,
            last_low=bias.last_low,
            prev_low=bias.prev_low,
        )
        if bias.direction == 0:
            return reject(f"bias_{bias.reason}")
        side = bias.direction
        lv = day_levels(mk, day, i, cfg.daily_rollover_hour)
        ev(
            "levels",
            pdh=lv.pdh,
            pdl=lv.pdl,
            asia_h=lv.asia_h,
            asia_l=lv.asia_l,
            nwog_lo=lv.nwog_lo,
            nwog_hi=lv.nwog_hi,
        )
        refs: list[Ref] = []
        if "PD" in cfg.sweep_refs:
            refs.append(
                Ref("PDL", lv.pdl, lv.pd_created_ns)
                if side == 1
                else Ref("PDH", lv.pdh, lv.pd_created_ns)
            )
        if "ASIA" in cfg.sweep_refs:
            a = lv.asia_l if side == 1 else lv.asia_h
            if math.isnan(a):
                ev("asia_missing")
            else:
                refs.append(Ref("ASIA_LOW" if side == 1 else "ASIA_HIGH", a, lv.asia_created_ns))
        if any(mk.contaminated(r.created_ns, w1) for r in refs):  # R5a
            return reject("reference_window_contaminated")

        not_before, expired = ny_ns(day, cfg.window_start), False
        while True:
            st, why = self._setup(day, side, bias, lv, refs, not_before, res.events)
            if st is None:
                if expired:
                    ev("rescan_ended", reason=why)
                    return reject("unfilled_expired")
                return reject(why)
            o = st.order
            ev(
                "order_created",
                st.fvg.formed_ns,
                limit=o.limit,
                stop=o.stop,
                target=st.target.price,
                target_name=st.target.name,
                planned_rr=st.target.rr,
            )
            fi = find_fill(mk, side, o.limit, st.fvg.formed_ns, t_exp)
            if fi >= 0:
                break
            ev("order_expired_cancelled", t_exp)
            expired, not_before = True, t_exp  # R12: one pending order; re-scan after cancellation

        ev("order_filled", int(mk.ts[fi]), price=o.limit)
        ex = run_exit(mk, side, fi, o.stop, st.target.price, t_close, cfg.slippage)
        r = realized_r(side, o.limit, ex.price, st.target.unit, cfg.commission_pts)
        ev(
            "exit",
            int(mk.ts[ex.idx]),
            reason=ex.reason,
            price=ex.price,
            r=r,
            data_gap=ex.data_gap,
            gap_through=ex.gap_through,
        )
        jp = mk.idx(st.fvg.formed_ns) - 1
        place_px = float(mk.ask["c"][jp] if side == 1 else mk.bid["c"][jp])
        res.reason = "trade"
        res.trade = {
            "instrument": mk.instrument,
            "trading_date": day.isoformat(),
            "session": SESSION,
            "side": side,
            "htf_bias": bias.reason,
            "liquidity_ref": st.sweep.ref_name,
            "liquidity_ref_price": st.sweep.ref_price,
            "liquidity_ref_created": _iso(st.sweep.ref_created_ns),
            "sweep_ts": _iso(st.sweep.start_ns),
            "sweep_price": st.sweep.extreme,
            "smt_status": st.smt_status,
            "mss_ts": _iso(st.mss.end_ns),
            "mss_broken_swing": st.mss.swing_price,
            "displacement_candle_ts": _iso(st.fvg.c2_start_ns),
            "fvg_bottom": st.fvg.bottom,
            "fvg_top": st.fvg.top,
            "fvg_tf": f"{cfg.fvg_tf_min}m",
            "fvg_formed_ts": _iso(st.fvg.formed_ns),
            "placed_ns": st.fvg.formed_ns,
            "placement_px": place_px,
            "pd_state": st.pd_state,
            "equilibrium": st.eq,
            "entry_model": cfg.entry_model,
            "ote_lo": st.ote[0],
            "ote_hi": st.ote[1],
            "limit": o.limit,
            "stop": o.stop,
            "target": st.target.price,
            "target_name": st.target.name,
            "r_unit": st.target.unit,
            "planned_rr": st.target.rr,
            "fill_ts": _iso(int(mk.ts[fi])),
            "fill_price": o.limit,
            "exit_ts": _iso(int(mk.ts[ex.idx])),
            "exit_price": ex.price,
            "exit_reason": ex.reason,
            "gap_through": ex.gap_through,
            "slippage": cfg.slippage if ex.reason != "target" else 0.0,
            "commission": cfg.commission_pts,
            "pnl_pts": (ex.price - o.limit) * side - cfg.commission_pts,
            "r": r,
            "data_gap": ex.data_gap,
            "repeated_m1_bars_setup": int(mk.repeat[mk.idx(st.sweep.start_ns) : fi + 1].sum()),
            "fill_i": fi,
            "exit_i": ex.idx,
            "config": cfg.fingerprint(),
        }
        return res

    def run(self, days: list[dt.date]) -> tuple[pd.DataFrame, pd.DataFrame, list[Event]]:
        trades, log, events = [], [], []
        for d in days:
            r = self.run_day(d)
            log.append({"day": d.isoformat(), "result": r.reason})
            events.extend(r.events)
            if r.trade is not None:
                trades.append(r.trade)
        return pd.DataFrame(trades), pd.DataFrame(log), events


def summarize(r: np.ndarray) -> dict[str, float]:
    """PF, expectancy, win rate, max DD (R), equity-curve R^2 (spec §13)."""
    n = len(r)
    if n == 0:
        return {"trades": 0}
    loss = -r[r < 0].sum()
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.r_[0.0, eq]) - np.r_[0.0, eq]).max())
    r2 = float(np.corrcoef(np.arange(n), eq)[0, 1] ** 2) if n > 2 and eq.std() > 0 else float("nan")
    return {
        "trades": n,
        "pf": float(r[r > 0].sum() / loss) if loss > 0 else float("inf"),
        "expectancy_r": float(r.mean()),
        "win_rate": float((r > 0).mean()),
        "max_dd_r": dd,
        "equity_r2": r2,
        "total_r": float(r.sum()),
    }
