"""Cycle 21 INDEPENDENT reference implementation, written from spec v1.2 text only.

It imports nothing from `v17.smc_sb` (only numpy, pandas and the XNYS calendar). Used by
`c21_reference_check.py` to compare day-by-day outcomes and trade-by-trade fields against the main engine.
"""

# ruff: noqa: PLR0912, PLR0915, E501, N806, C416, RUF059
from __future__ import annotations

import math
from bisect import bisect_left
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pandas_market_calendars as pmc

TZ = "America/New_York"
MIN = 60_000_000_000


def t_ns(d: date, hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return pd.Timestamp(datetime(d.year, d.month, d.day, h, m), tz=TZ).value


class RefMarket:
    def __init__(
        self,
        raw: pd.DataFrame,
        name: str,
        xnys: list[date] | None = None,
        early: list[date] | None = None,
        stale_run: int = 30,
    ) -> None:
        df = raw.sort_values("ts_utc").reset_index(drop=True)
        wall = pd.to_datetime(df.ts_utc, unit="ns", utc=True).dt.tz_convert(TZ).dt.tz_localize(None)
        tdate = (wall + pd.Timedelta(hours=7)).dt.normalize()
        # spec R27: crossed quotes on any field
        crossed = np.zeros(len(df), bool)
        for f in "ohlc":
            crossed |= (df["ask_" + f] < df["bid_" + f]).to_numpy()
        # spec R31: run >= stale_run of bars where one side is flat & unchanged while the other side moves
        frozen = np.zeros(len(df), bool)
        for a, b in (("ask", "bid"), ("bid", "ask")):
            A = df[[a + "_o", a + "_h", a + "_l", a + "_c"]]
            B = df[[b + "_o", b + "_h", b + "_l", b + "_c"]]
            flat = (A.nunique(axis=1) == 1).to_numpy()
            same = (A.diff().abs().sum(axis=1) == 0).to_numpy()
            moved = (B.diff().abs().sum(axis=1) > 0).to_numpy()
            cond = flat & same & moved
            cond[0] = False
            run_id = np.cumsum(~cond)
            sizes = pd.Series(cond.astype(int)).groupby(run_id).transform("sum").to_numpy()
            frozen |= cond & (sizes >= stale_run)
        bad = set(tdate[crossed | frozen])
        self.excluded = {d.date() for d in bad}
        self.excluded_ranges = [
            (t_ns(d - timedelta(days=1), "17:00"), t_ns(d, "17:00")) for d in self.excluded
        ]
        keep = ~tdate.isin(bad).to_numpy()
        df, wall, tdate = (
            df[keep].reset_index(drop=True),
            wall[keep].reset_index(drop=True),
            tdate[keep].reset_index(drop=True),
        )
        if xnys is None:
            sched = pmc.get_calendar("XNYS").schedule(
                start_date=str(tdate.min().date()), end_date=str(tdate.max().date())
            )
            xnys = [d.date() for d in sched.index]
            closes = pd.DatetimeIndex(sched.market_close).tz_convert(TZ)
            early = [d.date() for d, c in zip(sched.index, closes, strict=True) if c.hour < 16]
        self.xnys, self.early = set(xnys), set(early or [])
        self.name = name
        self.ts = df.ts_utc.to_numpy(np.int64)
        self.B = {f: df["bid_" + f].to_numpy(float) for f in "ohlc"}
        self.A = {f: df["ask_" + f].to_numpy(float) for f in "ohlc"}
        self.M = {f: (self.B[f] + self.A[f]) / 2 for f in "ohlc"}
        mid = pd.DataFrame({k: v for k, v in self.M.items()})
        mid["ts"] = self.ts

        def candles(minutes: int) -> pd.DataFrame:
            g = mid.groupby(mid.ts // (minutes * MIN))
            out = g.agg(
                o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")
            ).reset_index()
            out["start"] = out["ts"] * minutes * MIN
            out["end"] = out["start"] + minutes * MIN
            return out[["start", "end", "o", "h", "l", "c"]]

        self.c5, self.c15 = candles(5), candles(15)
        mid["td"] = tdate.to_numpy()
        d = mid.groupby("td").agg(h=("h", "max"), l=("l", "min"))
        self.daily = d[[x.date() in self.xnys for x in d.index]]
        self.daily_dates = [x.date() for x in self.daily.index]
        a = mid[wall.dt.hour.to_numpy() >= 20].groupby("td").agg(h=("h", "max"), l=("l", "min"))
        self.asia = {x.date(): (r.h, r.l) for x, r in a.iterrows()}
        self.c15_hi, self.c15_lo = self.c15.h.tolist(), self.c15.l.tolist()
        self.piv15 = {1: strict_pivots(self.c15_hi, True), -1: strict_pivots(self.c15_lo, False)}
        self.c5_lists = (
            self.c5.start.tolist(),
            self.c5.end.tolist(),
            self.c5.h.tolist(),
            self.c5.l.tolist(),
            self.c5.c.tolist(),
        )
        self.c15_lists = (self.c15.start.tolist(), self.c15.end.tolist(), self.c15.c.tolist())
        self.c5_pos = {s: k for k, s in enumerate(self.c5_lists[0])}

    def i(self, t: int) -> int:
        return int(np.searchsorted(self.ts, t))

    def dirty(self, a: int, b: int) -> bool:
        return any(lo < b and hi > a for lo, hi in self.excluded_ranges)

    def nwog(self, d: date) -> tuple[float, float, int]:
        sun = d - timedelta(days=d.weekday() + 1)
        s18 = t_ns(sun, "18:00")
        jc = self.i(t_ns(sun - timedelta(days=2), "17:00")) - 1
        jo = self.i(s18)
        if jc < 0 or self.ts[jc] < t_ns(sun - timedelta(days=3), "17:00"):
            return math.nan, math.nan, s18
        if jo >= len(self.ts) or self.ts[jo] >= t_ns(sun + timedelta(days=1), "17:00"):
            return math.nan, math.nan, s18
        x, y = self.M["c"][jc], self.M["o"][jo]
        if x == y:
            return math.nan, math.nan, s18
        return min(x, y), max(x, y), s18


def strict_pivots(vals: list[float], hi: bool) -> list[int]:
    out = []
    for k in range(2, len(vals) - 2):
        nb = [vals[k - 2], vals[k - 1], vals[k + 1], vals[k + 2]]
        if (hi and all(vals[k] > v for v in nb)) or (not hi and all(vals[k] < v for v in nb)):
            out.append(k)
    return out


def run_day(
    m: RefMarket,
    d: date,
    model: str = "A",
    smt: RefMarket | None = None,
    expiry: str = "11:05",
    slip: float = 0.5,
    comm: float = 0.0,
) -> tuple[str, dict | None]:
    if d not in m.xnys:
        return "not_xnys_session", None
    if d in m.excluded:
        return "excluded_session_bad_quotes", None
    if d in m.early:
        return "early_close_day", None
    w0, w1, exp, close16 = t_ns(d, "10:00"), t_ns(d, "11:00"), t_ns(d, expiry), t_ns(d, "16:00")
    a, b = t_ns(d, "09:30"), exp
    if m.i(b) - m.i(a) != (b - a) // MIN:
        return "missing_m1", None
    if d not in m.daily_dates:
        return "no_daily_session", None
    pos = m.daily_dates.index(d)
    if pos == 0:
        return "no_previous_day", None
    hs, ls = m.daily.h.tolist()[:pos], m.daily.l.tolist()[:pos]
    ph, pl = strict_pivots(hs, True), strict_pivots(ls, False)
    if len(ph) < 2 or len(pl) < 2:
        return "bias_insufficient_structure", None
    H1, H0, L1, L0 = hs[ph[-1]], hs[ph[-2]], ls[pl[-1]], ls[pl[-2]]
    if H1 > H0 and L1 > L0:
        side = 1
    elif H1 < H0 and L1 < L0:
        side = -1
    else:
        return "bias_mixed_or_equal", None
    eq = (H1 + L1) / 2
    prev = m.daily_dates[pos - 1]
    pdh, pdl = float(hs[-1]), float(ls[-1])
    pd_created = t_ns(prev, "17:00")
    refs = [("PDL", pdl, pd_created) if side == 1 else ("PDH", pdh, pd_created)]
    if d in m.asia:
        ah, al = m.asia[d]
        refs.append(
            ("ASIA_LOW", float(al), t_ns(d, "00:00"))
            if side == 1
            else ("ASIA_HIGH", float(ah), t_ns(d, "00:00"))
        )
    if any(m.dirty(r[2], w1) for r in refs):
        return "reference_window_contaminated", None
    nlo, nhi, nstart = m.nwog(d)

    c5s, c5e, c5h, c5l, c5c = m.c5_lists
    c15s, c15e, c15c = m.c15_lists
    start_pos = m.c5_pos

    not_before, had_order = w0, False
    while True:
        # ---- sweep (first breach since creation) ----
        best = None
        for name, lvl, created in refs:
            i0, i1 = m.i(created), m.i(w1)
            arr = m.M["l"][i0:i1] if side == 1 else m.M["h"][i0:i1]
            hit = np.nonzero(arr < lvl)[0] if side == 1 else np.nonzero(arr > lvl)[0]
            if len(hit) == 0:
                continue
            t = int(m.ts[i0 + hit[0]])
            cs = t - t % (5 * MIN)
            if cs < w0 or cs < not_before or cs not in start_pos:
                continue
            k = start_pos[cs]
            if c5e[k] > w1:
                continue
            if (side == 1 and not c5c[k] > lvl) or (side == -1 and not c5c[k] < lvl):
                continue
            ext = c5l[k] if side == 1 else c5h[k]
            if best is None or cs < best[0]:
                best = (cs, name, lvl, ext)
        if best is None:
            return ("unfilled_expired" if had_order else "no_sweep"), None
        sw_s, sw_name, sw_lvl, sw_ext = best
        sw_e = sw_s + 5 * MIN
        smt_status = "disabled"
        if smt is not None:
            if d not in smt.daily_dates or smt.daily_dates.index(d) == 0:
                return ("unfilled_expired" if had_order else "smt_partner_missing"), None
            q = smt.daily_dates.index(d)
            pref = {
                "PDL": smt.daily.l.tolist()[q - 1],
                "PDH": smt.daily.h.tolist()[q - 1],
                "ASIA_LOW": smt.asia.get(d, (math.nan, math.nan))[1],
                "ASIA_HIGH": smt.asia.get(d, (math.nan, math.nan))[0],
            }[sw_name]
            if math.isnan(pref):
                return ("unfilled_expired" if had_order else "smt_partner_ref_missing"), None
            mine = [s for s, e in zip(c5s, c5e, strict=True) if s >= w0 and e <= sw_e]
            pc = smt.c5[(smt.c5.start >= w0) & (smt.c5.end <= sw_e)]
            if not mine or mine != pc.start.tolist():
                return ("unfilled_expired" if had_order else "smt_unsynchronized"), None
            held = pc.l.min() > pref if side == 1 else pc.h.max() < pref
            smt_status = "smt_divergence" if held else "smt_no_divergence"
            if not held:
                return ("unfilled_expired" if had_order else "smt_no_divergence"), None
        # ---- MSS on 15 m ----
        piv = m.piv15[side]
        mss = None
        for k15 in range(bisect_left(c15s, w0), bisect_left(c15s, w1)):
            if not (c15s[k15] >= w0 and c15e[k15] <= w1 and c15e[k15] > sw_e):
                continue
            j = bisect_left(piv, k15 - 2)  # pivots p with p + 2 <= k15 - 1  <=>  p < k15 - 2
            if j == 0:
                continue
            swing = (m.c15_hi if side == 1 else m.c15_lo)[piv[j - 1]]
            if (side == 1 and c15c[k15] > swing) or (side == -1 and c15c[k15] < swing):
                mss = (c15e[k15], swing)
                break
        if mss is None:
            return ("unfilled_expired" if had_order else "no_mss"), None
        # ---- FVG on 5 m ----
        fvg = None
        for k3 in range(max(2, bisect_left(c5s, w0)), bisect_left(c5s, w1)):
            if not (c5e[k3] >= mss[0] and c5e[k3] <= w1):
                continue
            if c5s[k3] - c5s[k3 - 2] != 10 * MIN or c5s[k3] - c5s[k3 - 1] != 5 * MIN:
                continue
            if side == 1 and c5l[k3] > c5h[k3 - 2]:
                fvg = (c5h[k3 - 2], c5l[k3], c5e[k3])  # bottom, top, formed
                break
            if side == -1 and c5h[k3] < c5l[k3 - 2]:
                fvg = (c5h[k3], c5l[k3 - 2], c5e[k3])
                break
        if fvg is None:
            return ("unfilled_expired" if had_order else "no_fvg_after_mss"), None
        bottom, top, placed = fvg
        limit, stop = (top, bottom) if side == 1 else (bottom, top)
        if model == "B":
            ia, ib = m.i(sw_s), m.i(mss[0])
            if side == 1:
                H = m.M["h"][ia:ib].max()
                zlo, zhi = H - 0.79 * (H - sw_ext), H - 0.62 * (H - sw_ext)
            else:
                L = m.M["l"][ia:ib].min()
                zlo, zhi = L + 0.62 * (sw_ext - L), L + 0.79 * (sw_ext - L)
            if not (zlo <= limit <= zhi):
                return ("unfilled_expired" if had_order else "ote_proximal_outside_zone"), None
        if not ((side == 1 and limit < eq) or (side == -1 and limit > eq)):
            return ("unfilled_expired" if had_order else "premium_discount_fail"), None
        # ---- target ----
        if m.dirty(pd_created, placed) or (not math.isnan(nlo) and m.dirty(nstart, placed)):
            return ("unfilled_expired" if had_order else "reference_window_contaminated"), None
        unit = abs(limit - stop) + slip + comm
        opts = []
        i0, i1 = m.i(pd_created), m.i(placed)
        lo_w = m.M["l"][i0:i1].min() if i1 > i0 else None
        hi_w = m.M["h"][i0:i1].max() if i1 > i0 else None
        for name, lvl in (("PDH", pdh), ("PDL", pdl)):
            touched = lo_w is not None and lo_w <= lvl <= hi_w
            if (lvl - limit) * side > 0 and not touched:
                opts.append((abs(lvl - limit), name, lvl))
        if not math.isnan(nlo):
            j0 = m.i(nstart)
            inside = i1 > j0 and m.M["l"][j0:i1].min() < nhi and m.M["h"][j0:i1].max() > nlo
            name, lvl = ("NWOG_LO", nlo) if side == 1 else ("NWOG_HI", nhi)
            if (lvl - limit) * side > 0 and not inside:
                opts.append((abs(lvl - limit), name, lvl))
        tgt = None
        for _, name, lvl in sorted(opts):
            if abs(lvl - limit) - comm >= 2.0 * unit:
                tgt = (name, lvl)
                break
        if tgt is None:
            return ("unfilled_expired" if had_order else "no_target_min_rr"), None
        # ---- fill ----
        fill = None
        for x in range(m.i(placed), m.i(exp)):
            if (side == 1 and m.A["l"][x] <= limit) or (side == -1 and m.B["h"][x] >= limit):
                fill = x
                break
        if fill is None:
            had_order, not_before = True, exp
            continue
        break
    # ---- exit ----
    last = max(m.i(close16) - 1, fill)
    gap16 = m.i(close16) - 1 < 0 or m.ts[m.i(close16) - 1] != close16 - MIN
    reason = None
    for x in range(fill, last + 1):
        if side == 1 and m.B["l"][x] <= stop:
            base = m.B["o"][x] if m.B["o"][x] < stop else stop
            reason, px, ex_i, gap = "stop", base - slip, x, base != stop
            break
        if side == -1 and m.A["h"][x] >= stop:
            base = m.A["o"][x] if m.A["o"][x] > stop else stop
            reason, px, ex_i, gap = "stop", base + slip, x, base != stop
            break
        if x > fill and (
            (side == 1 and m.B["h"][x] >= tgt[1]) or (side == -1 and m.A["l"][x] <= tgt[1])
        ):
            reason, px, ex_i, gap = "target", tgt[1], x, False
            break
    data_gap = False
    if reason is None:
        px = (m.B["c"][last] - slip) if side == 1 else (m.A["c"][last] + slip)
        reason, ex_i, gap, data_gap = "force_close_16", last, False, bool(gap16)
    r = ((px - limit) * side - comm) / unit
    return "trade", {
        "side": side,
        "ref": sw_name,
        "sweep_ns": sw_s,
        "mss_ns": mss[0],
        "swing": mss[1],
        "fvg_bottom": bottom,
        "fvg_top": top,
        "limit": limit,
        "stop": stop,
        "target_name": tgt[0],
        "target": tgt[1],
        "fill_ns": int(m.ts[fill]),
        "exit_ns": int(m.ts[ex_i]),
        "exit_reason": reason,
        "exit_price": px,
        "gap_through": gap,
        "data_gap": data_gap,
        "r": r,
        "smt": smt_status,
    }
