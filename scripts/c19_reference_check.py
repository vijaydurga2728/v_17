"""Cycle 19 independent re-implementation check: Silver Bullet v4, NY AM, exam period 2015-2017.

Written from the pre-reg text (c4461e8). Shares only the M1 loader and the c17 reference pandas frame with the main code.
"""
# ruff: noqa: PLR0912, PLR0915, E501, C901
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from c17_reference_check import frame  # noqa: E402
from run_c17_silver_bullet import load  # noqa: E402
from v17.setups import c17_silver_bullet as main  # noqa: E402  (only to run the main engine for comparison)

C = {"USATECHIDXUSD": dict(bmin=2.0, frame=10.0, slip=0.5, comm=0.0),
     "EURUSD": dict(bmin=0.0002, frame=0.0015, slip=0.00005, comm=0.00006)}
START, END = "2015-01-01", "2017-12-31"
NYZ = "America/New_York"


def ref(df: pd.DataFrame, sym: str) -> list[tuple]:
    c = C[sym]
    df = df[(df.t >= pd.Timestamp("2014-11-01", tz=NYZ)) & (df.t < pd.Timestamp("2018-01-03", tz=NYZ))].reset_index(drop=True)
    nyday = df.t.dt.tz_localize(None).dt.normalize()
    daily = df.groupby(nyday).agg(h=("mh", "max"), l=("ml", "min"))
    daily = daily[daily.index.dayofweek < 5]
    out = []
    for day in pd.bdate_range(START, END):
        if day not in daily.index:
            continue
        prev = daily[daily.index < day]
        if len(prev) == 0:
            continue
        pdh, pdl = prev.h.iloc[-1], prev.l.iloc[-1]
        mon = day - pd.Timedelta(days=day.dayofweek)
        pw = daily[(daily.index >= mon - pd.Timedelta(days=7)) & (daily.index < mon)]
        pwh, pwl = (pw.h.max(), pw.l.min()) if len(pw) else (float("nan"), float("nan"))
        d0 = pd.Timestamp(day).tz_localize(NYZ)
        ws_t, we_t = d0 + pd.Timedelta(hours=10), d0 + pd.Timedelta(hours=11)
        idx = lambda t: int(df.t.searchsorted(t))  # noqa: E731
        i_day, i_ph, ws, we = idx(d0), idx(ws_t - pd.Timedelta(minutes=60)), idx(ws_t), idx(we_t)
        i_exp, hard = idx(we_t + pd.Timedelta(minutes=5)), idx(we_t + pd.Timedelta(minutes=60)) - 1
        if not (ws > i_day and ws > i_ph and we > ws + 3 and hard >= we):
            continue
        # 1 draw
        px = df.mo.iat[ws]
        hb, lb = df.mh.iloc[i_day:ws].max(), df.ml.iloc[i_day:ws].min()
        cand = [(abs(v - px), v) for v, hi in ((pdh, 1), (pwh, 1), (pdl, 0), (pwl, 0))
                if pd.notna(v) and not (hi and hb > v) and not ((not hi) and lb < v)
                and ((hi and v > px) or ((not hi) and v < px))]
        if not cand:
            continue
        draw = min(cand)[1]
        side = 1 if draw > px else -1
        # 2 sweep
        if side == 1:
            lvl = max(df.ml.iloc[i_day:ws].min(), df.ml.iloc[i_ph:ws].min())
            sw = next((k for k in range(ws, we) if df.ml.iat[k] < lvl), None)
        else:
            lvl = min(df.mh.iloc[i_day:ws].max(), df.mh.iloc[i_ph:ws].max())
            sw = next((k for k in range(ws, we) if df.mh.iat[k] > lvl), None)
        if sw is None:
            continue
        # 3 short-term swing + MSS
        ref_lvl = None
        j = sw - 2
        while j >= i_day + 1:
            if side == 1 and df.mh.iat[j] > df.mh.iat[j - 1] and df.mh.iat[j] > df.mh.iat[j + 1]:
                ref_lvl = df.mh.iat[j]
                break
            if side == -1 and df.ml.iat[j] < df.ml.iat[j - 1] and df.ml.iat[j] < df.ml.iat[j + 1]:
                ref_lvl = df.ml.iat[j]
                break
            j -= 1
        if ref_lvl is None:
            continue
        mss = next((m for m in range(sw + 1, we) if (df.mc.iat[m] > ref_lvl if side == 1 else df.mc.iat[m] < ref_lvl)), None)
        if mss is None:
            continue
        # 4-6 displacement FVG, premium/discount, order
        setup = None
        for k3 in range(sw + 1, we):
            k2, k1 = k3 - 1, k3 - 2
            if k2 < sw or k2 > mss:
                continue
            if pd.isna(df.atr.iat[k1]):
                continue
            top, bot = (df.ml.iat[k3], df.mh.iat[k1]) if side == 1 else (df.ml.iat[k1], df.mh.iat[k3])
            if top <= bot:
                continue
            rng = df.mh.iat[k2] - df.ml.iat[k2]
            if rng <= 0 or abs(df.mc.iat[k2] - df.mo.iat[k2]) / rng < 0.65 or rng < 1.5 * df.atr.iat[k1]:
                continue
            if top - bot < 2 * (df.ac.iat[k3] - df.bc.iat[k3]):
                continue
            ce = (top + bot) / 2
            mid = (pdh + pdl) / 2
            if (side == 1 and ce >= mid) or (side == -1 and ce <= mid):
                break
            last = max(k3, mss)
            ext = df.ml.iloc[sw:last + 1].min() if side == 1 else df.mh.iloc[sw:last + 1].max()
            dist = max((ce - (ext - side * c["bmin"])) * side, c["bmin"])
            tpd = (draw - ce) * side
            if tpd < c["frame"] or tpd / dist < 2.0:
                break
            setup = (last, ce, ce - side * dist, draw, dist)
            break
        if setup is None:
            continue
        last, ce, sl, tp, dist = setup
        fill = next((k for k in range(last + 1, i_exp)
                     if (side == 1 and df.al.iat[k] <= ce) or (side == -1 and df.bh.iat[k] >= ce)), None)
        if fill is None:
            continue
        reason, epx = 3, (df.bc.iat[hard] if side == 1 else df.ac.iat[hard])
        for k in range(fill, hard + 1):
            if (side == 1 and df.bl.iat[k] <= sl) or (side == -1 and df.ah.iat[k] >= sl):
                reason, epx = 1, sl
                break
            if k > fill and ((side == 1 and df.bh.iat[k] >= tp) or (side == -1 and df.al.iat[k] <= tp)):
                reason, epx = 2, tp
                break
        slip = 0.0 if reason == 2 else c["slip"]
        epx = epx - slip if side == 1 else epx + slip
        out.append((day.date(), side, reason, round(ce, 8), round(sl, 8), ((epx - ce) * side - c["comm"]) / dist))
    return out


def run() -> int:
    ok_all = True
    for sym in ("USATECHIDXUSD", "EURUSD"):
        b = load(sym)
        days = main.day_table(b, "AM", START, END)
        m = main.run_slot_v4(b, days, main.SPECS[sym], sym)
        a = [(pd.Timestamp(r.day).date(), int(r.side), int(r.reason), round(r.entry, 8), round(r.sl, 8), r.r)
             for r in m.itertuples()]
        r_ = ref(frame(sym), sym)
        same = len(a) == len(r_) and all(x[:5] == y[:5] for x, y in zip(a, r_, strict=False))
        dr = max((abs(x[5] - y[5]) for x, y in zip(a, r_, strict=False)), default=0.0)
        if not same:
            sa, sr = {x[:5] for x in a}, {y[:5] for y in r_}
            print("   only main:", sorted(sa - sr)[:4], "\n   only ref:", sorted(sr - sa)[:4])
        ok = bool(same and dr < 1e-9)
        ok_all &= ok
        print(f"{sym} AM exam 2015-2017 v4: main {len(a)} ref {len(r_)} keys_equal {same} max|dR| {dr:.2e} -> "
              f"{'MATCH' if ok else 'MISMATCH'}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(run())
