"""Cycle 18b independent re-implementation check: Silver Bullet v3 + swing stop, holdout 2025 → end, NY AM.

Written from the pre-reg text; shares only the M1 loader and the c17 reference frame builder with nothing from the
main v3 logic. Compares trade by trade for NAS100 and EURUSD.
"""
# ruff: noqa: PLR0912, PLR0915, E501, C901
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from c17_reference_check import frame  # noqa: E402  (independent pandas frame + ATR)
from run_c17_silver_bullet import load  # noqa: E402
from v17.setups import c17_silver_bullet as main  # noqa: E402  (only to run the main engine for comparison)

C = {"USATECHIDXUSD": dict(bmin=2.0, frame=10.0, slip=0.5, comm=0.0),
     "EURUSD": dict(bmin=0.0002, frame=0.0015, slip=0.00005, comm=0.00006)}
START, END = "2025-01-01", "2026-12-31"


def ref(df: pd.DataFrame, sym: str) -> list[tuple]:
    c = C[sym]
    df = df[df.t >= pd.Timestamp("2024-11-01", tz="America/New_York")]
    pos = pd.Series(range(len(df)), index=df.index)
    df = df.reset_index(drop=True)
    pos = pd.Series(range(len(df)), index=df.t)
    nyday = df.t.dt.tz_localize(None).dt.normalize()
    daily = df.groupby(nyday).agg(h=("mh", "max"), l=("ml", "min"))
    daily = daily[daily.index.dayofweek < 5]
    out = []
    for day in pd.bdate_range(START, END):
        prev = daily[daily.index < day]
        if len(prev) == 0 or day not in daily.index:
            continue
        pdh, pdl = prev.h.iloc[-1], prev.l.iloc[-1]
        wk_start = day - pd.Timedelta(days=day.dayofweek)          # this Monday
        pw = daily[(daily.index >= wk_start - pd.Timedelta(days=7)) & (daily.index < wk_start)]
        pwh, pwl = (pw.h.max(), pw.l.min()) if len(pw) else (float("nan"), float("nan"))
        d0 = pd.Timestamp(day).tz_localize("America/New_York")
        ws, we = d0 + pd.Timedelta(hours=10), d0 + pd.Timedelta(hours=11)
        pre = df[(df.t >= d0) & (df.t < ws)]
        win = df[(df.t >= ws) & (df.t < we)]
        hard = df[df.t < we + pd.Timedelta(minutes=60)]
        if len(pre) == 0 or len(win) <= 3 or len(hard) == 0 or hard.t.iloc[-1] < we:
            continue
        if len(df[(df.t >= ws - pd.Timedelta(minutes=60)) & (df.t < ws)]) == 0:
            continue
        hard_k = len(hard) - 1
        px = win.mo.iloc[0]
        lv = []
        for v, is_hi in ((pdh, True), (pwh, True), (pdl, False), (pwl, False)):
            if pd.isna(v):
                continue
            if is_hi and pre.mh.max() > v:
                continue
            if (not is_hi) and pre.ml.min() < v:
                continue
            if (is_hi and v > px) or ((not is_hi) and v < px):
                lv.append((abs(v - px), v))
        if not lv:
            continue
        draw = min(lv)[1]
        side = 1 if draw > px else -1
        k_ws = int(pos[win.t.iloc[0]])
        k_last = int(pos[win.t.iloc[-1]])
        setup = None
        for k3 in range(k_ws + 2, k_last + 1):
            k1 = k3 - 2
            top, bot = (df.ml.iat[k3], df.mh.iat[k1]) if side == 1 else (df.ml.iat[k1], df.mh.iat[k3])
            if top <= bot:
                continue
            ce = (top + bot) / 2
            if (draw - ce) * side < c["frame"]:
                continue
            if side == 1:
                stop = df.ml.iloc[k_ws:k1 + 1].min() - c["bmin"]
            else:
                stop = df.mh.iloc[k_ws:k1 + 1].max() + c["bmin"]
            dist = max((ce - stop) * side, c["bmin"])
            setup = (k3, ce, ce - side * dist, draw, dist)
            break
        if setup is None:
            continue
        k3, ce, sl, tp, dist = setup
        exp_n = len(df[df.t < we + pd.Timedelta(minutes=5)])
        fill = next((k for k in range(k3 + 1, exp_n)
                     if (side == 1 and df.al.iat[k] <= ce) or (side == -1 and df.bh.iat[k] >= ce)), None)
        if fill is None:
            continue
        reason, epx, xk = 3, (df.bc.iat[hard_k] if side == 1 else df.ac.iat[hard_k]), hard_k
        for k in range(fill, hard_k + 1):
            if side == 1 and df.bl.iat[k] <= sl:
                reason, epx, xk = 1, sl, k
                break
            if side == -1 and df.ah.iat[k] >= sl:
                reason, epx, xk = 1, sl, k
                break
            if k > fill and side == 1 and df.bh.iat[k] >= tp:
                reason, epx, xk = 2, tp, k
                break
            if k > fill and side == -1 and df.al.iat[k] <= tp:
                reason, epx, xk = 2, tp, k
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
        m = main.run_slot_v3(b, days, main.SPECS[sym], sym, stop_mode="swing")
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
        print(f"{sym} AM holdout v3-A: main {len(a)} ref {len(r_)} keys_equal {same} max|dR| {dr:.2e} -> "
              f"{'MATCH' if ok else 'MISMATCH'}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(run())
