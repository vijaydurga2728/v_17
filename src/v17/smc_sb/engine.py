"""Cycle 21 per-day pipeline: every stage records an event; every rejection records its reason (spec §12)."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from v17.smc_sb.config import StrategyConfig
from v17.smc_sb.data import Market
from v17.smc_sb.entry_models import model_a, model_b_ok
from v17.smc_sb.execution import find_fill, run_exit
from v17.smc_sb.fvg import find_fvg
from v17.smc_sb.liquidity import day_levels, select_target
from v17.smc_sb.market_bias import DailyStructure
from v17.smc_sb.premium_discount import eligible, equilibrium, zone
from v17.smc_sb.risk import realized_r
from v17.smc_sb.session import NS_PER_MIN, ny_ns
from v17.smc_sb.smt import smt_divergence
from v17.smc_sb.structure import find_mss, pivot_flags
from v17.smc_sb.sweep import find_sweep

SESSION = "NY_AM_10_11"


def _iso(ns: int) -> str:
    return pd.Timestamp(ns, tz="UTC").tz_convert("America/New_York").isoformat()


@dataclass
class DayResult:
    day: dt.date
    reason: str  # "trade" or a rejection reason
    events: list[dict[str, object]] = field(default_factory=list)
    trade: dict[str, object] | None = None


class Engine:
    def __init__(self, mk: Market, cfg: StrategyConfig, partner: Market | None = None) -> None:
        if cfg.smt_enabled and partner is None:
            raise ValueError("SMT experiment requires a partner market")
        self.mk, self.cfg, self.partner = mk, cfg, partner
        self.ds = DailyStructure(mk.daily, cfg.daily_pivot_left, cfg.daily_pivot_right)
        self.ph15, self.pl15 = pivot_flags(
            mk.c15.h.to_numpy(), mk.c15.l.to_numpy(), cfg.mss_pivot_left, cfg.mss_pivot_right
        )

    def run_day(self, day: dt.date) -> DayResult:  # noqa: PLR0912, PLR0915
        mk, cfg = self.mk, self.cfg
        res = DayResult(day, "")

        def ev(stage: str, ns: int | None = None, /, **detail: object) -> None:
            res.events.append(
                {"day": day.isoformat(), "stage": stage, "ts": _iso(ns) if ns else "", **detail}
            )

        def reject(reason: str, **detail: object) -> DayResult:
            ev("rejected", reason=reason, **detail)
            res.reason = reason
            return res

        w0, w1 = ny_ns(day, cfg.window_start), ny_ns(day, cfg.window_end)
        t_chk, t_exp, t_close = (
            ny_ns(day, cfg.data_check_start),
            ny_ns(day, cfg.order_expiry),
            ny_ns(day, cfg.force_close),
        )
        # R20: complete M1 coverage in [09:30, 11:05) or the date is rejected (no substitution).
        expected = (t_exp - t_chk) // NS_PER_MIN
        have = mk.idx(t_exp) - mk.idx(t_chk)
        if have != expected:
            return reject("missing_m1", expected=int(expected), have=int(have))
        key = pd.Timestamp(day)
        i = mk.day_pos(key)
        if i < 0:
            return reject("no_daily_session")
        if i == 0:
            return reject("no_previous_day")
        # D1 bias
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
        # D2 sweep
        refs: dict[str, float] = {}
        if "PD" in cfg.sweep_refs:
            refs["PDL" if side == 1 else "PDH"] = lv.pdl if side == 1 else lv.pdh
        if "ASIA" in cfg.sweep_refs:
            a = lv.asia_l if side == 1 else lv.asia_h
            if math.isnan(a):
                ev("asia_missing")
            else:
                refs["ASIA_LOW" if side == 1 else "ASIA_HIGH"] = a
        sw = find_sweep(mk.c5, side, refs, w0, w1)
        if sw is None:
            return reject("no_sweep", refs=str(refs))
        ev("sweep", sw.start_ns, ref=sw.ref_name, ref_price=sw.ref_price, extreme=sw.extreme)
        # D11 SMT (experiment only)
        smt_status = "disabled"
        if cfg.smt_enabled:
            assert self.partner is not None
            p = self.partner
            pkey = pd.Timestamp(day)
            if p.day_pos(pkey) <= 0:
                return reject("smt_partner_missing")
            plv = day_levels(p, day, p.day_pos(pkey), cfg.daily_rollover_hour)
            pref = {
                "PDL": plv.pdl,
                "PDH": plv.pdh,
                "ASIA_LOW": plv.asia_l,
                "ASIA_HIGH": plv.asia_h,
            }[sw.ref_name]
            ok, why = smt_divergence(mk, p, side, pref, w0, sw.end_ns)
            smt_status = why
            ev("smt", partner=p.instrument, partner_ref=pref, result=why)
            if not ok:
                return reject(why)
        # D3 MSS
        mss, why = find_mss(
            mk.c15, self.ph15, self.pl15, side, sw.end_ns, w0, w1, cfg.mss_pivot_right
        )
        if mss is None:
            return reject(why)
        ev(
            "mss",
            mss.end_ns,
            close=mss.close,
            broken_swing=mss.swing_price,
            swing_ts=_iso(int(mk.c15.start.to_numpy()[mss.swing_idx])),
        )
        # D4-D6 FVG
        fvg = find_fvg(mk.c5, side, mss.end_ns, w1, cfg.fvg_tf_min)
        if fvg is None:
            return reject("no_fvg_after_mss")
        ev(
            "fvg",
            fvg.formed_ns,
            bottom=fvg.bottom,
            top=fvg.top,
            displacement_ts=_iso(fvg.c2_start_ns),
        )
        order = model_a(fvg, side)
        ote = (float("nan"), float("nan"))
        impulse = float("nan")
        if cfg.entry_model == "B":
            ia, ib = mk.idx(sw.start_ns), mk.idx(mss.end_ns)
            impulse = float(mk.mid["h"][ia:ib].max() if side == 1 else mk.mid["l"][ia:ib].min())
            ok_b, ote = model_b_ok(fvg, side, sw.extreme, impulse, cfg.ote_low, cfg.ote_high)
            ev(
                "ote",
                zone_lo=ote[0],
                zone_hi=ote[1],
                impulse_extreme=impulse,
                proximal=fvg.proximal,
            )
            if not ok_b:
                return reject("ote_proximal_outside_zone")
        # §8 premium / discount
        eq = equilibrium(bias)
        pd_state = zone(order.limit, eq)
        ev("premium_discount", equilibrium=eq, state=pd_state)
        if math.isnan(eq):
            return reject("no_daily_swing_range")
        if not eligible(side, order.limit, eq):
            return reject("premium_discount_fail", state=pd_state)
        # D13 target
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
        ev("targets", candidates=str(ts_.candidates))
        if ts_.target is None:
            return reject("no_target_min_rr")
        tg = ts_.target
        ev(
            "order_created",
            fvg.formed_ns,
            limit=order.limit,
            stop=order.stop,
            target=tg.price,
            target_name=tg.name,
            planned_rr=tg.rr,
        )
        # D8 fill
        fi = find_fill(mk, side, order.limit, fvg.formed_ns, t_exp)
        if fi < 0:
            ev("order_expired_cancelled", t_exp)
            return reject("unfilled_expired")
        ev("order_filled", int(mk.ts[fi]), price=order.limit)
        ex = run_exit(mk, side, fi, order.stop, tg.price, t_close, cfg.slippage)
        r = realized_r(side, order.limit, ex.price, tg.unit, cfg.commission_pts)
        ev("exit", int(mk.ts[ex.idx]), reason=ex.reason, price=ex.price, r=r, data_gap=ex.data_gap)
        res.reason = "trade"
        res.trade = {
            "instrument": mk.instrument,
            "trading_date": day.isoformat(),
            "session": SESSION,
            "side": side,
            "htf_bias": bias.reason,
            "liquidity_ref": sw.ref_name,
            "liquidity_ref_price": sw.ref_price,
            "sweep_ts": _iso(sw.start_ns),
            "sweep_price": sw.extreme,
            "smt_status": smt_status,
            "mss_ts": _iso(mss.end_ns),
            "mss_broken_swing": mss.swing_price,
            "displacement_candle_ts": _iso(fvg.c2_start_ns),
            "fvg_bottom": fvg.bottom,
            "fvg_top": fvg.top,
            "fvg_tf": f"{cfg.fvg_tf_min}m",
            "fvg_formed_ts": _iso(fvg.formed_ns),
            "pd_state": pd_state,
            "equilibrium": eq,
            "entry_model": cfg.entry_model,
            "ote_lo": ote[0],
            "ote_hi": ote[1],
            "limit": order.limit,
            "stop": order.stop,
            "target": tg.price,
            "target_name": tg.name,
            "r_unit": tg.unit,
            "planned_rr": tg.rr,
            "fill_ts": _iso(int(mk.ts[fi])),
            "fill_price": order.limit,
            "exit_ts": _iso(int(mk.ts[ex.idx])),
            "exit_price": ex.price,
            "exit_reason": ex.reason,
            "slippage": cfg.slippage if ex.reason != "target" else 0.0,
            "commission": cfg.commission_pts,
            "pnl_pts": (ex.price - order.limit) * side - cfg.commission_pts,
            "r": r,
            "data_gap": ex.data_gap,
            "fill_i": fi,
            "exit_i": ex.idx,
            "config": cfg.fingerprint(),
        }
        return res

    def run(
        self, days: list[dt.date]
    ) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
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
