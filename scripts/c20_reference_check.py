"""Cycle 20 independent re-implementation check: Silver Bullet v5 (NY AM, 2018 → end) for US30 and AUDUSD.

Written from the pre-reg text (4d802da). Shares only the M1 data loading with the main code.
"""
# ruff: noqa: PLR0912, PLR0915, E501, C901
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c20_silver_bullet_v5 import load_m1  # noqa: E402  (data loading only)
from v17.setups import c17_silver_bullet as base  # noqa: E402  (main engine: only to run it for comparison)
from v17.setups import c20_silver_bullet_v5 as main  # noqa: E402

NYZ = "America/New_York"
C = {"USA30IDXUSD": dict(bmin=2.0, frame=10.0, slip=0.5, comm=0.0, partner="USA500IDXUSD", rel=1),
     "AUDUSD": dict(bmin=0.0002, frame=0.0015, slip=0.00005, comm=0.00006, partner="DOLLARIDXUSD", rel=-1)}
START, END = "2018-01-01", "2026-12-31"


def frame(sym: str) -> pd.DataFrame:
    m = load_m1(sym).sort_values("ts_utc").drop_duplicates("ts_utc").reset_index(drop=True)
    df = pd.DataFrame({"ts": m.ts_utc.to_numpy(np.int64)})
    for s in "ohlc":
        df["b" + s], df["a" + s] = m[f"bid_{s}"].to_numpy(float), m[f"ask_{s}"].to_numpy(float)
        df["m" + s] = (df["b" + s] + df["a" + s]) / 2
    pc = df.mc.shift(1)
    tr = np.maximum.reduce([(df.mh - df.ml).to_numpy(), (df.mh - pc).abs().fillna(0).to_numpy(), (df.ml - pc).abs().fillna(0).to_numpy()])
    tr[0] = df.mh.iat[0] - df.ml.iat[0]
    df["atr"] = pd.Series(tr).rolling(14).mean()
    df["t"] = pd.to_datetime(df.ts, unit="ns", utc=True).dt.tz_convert(NYZ)
    return df


def ref(sym: str) -> list[tuple]:
    c = C[sym]
    df, pf = frame(sym), frame(c["partner"])
    ts, pts = df.ts.to_numpy(), pf.ts.to_numpy()
    nyday = df.t.dt.tz_localize(None).dt.normalize()
    daily = df.groupby(nyday).agg(h=("mh", "max"), l=("ml", "min"))
    daily = daily[daily.index.dayofweek < 5]
    dlist = list(daily.index)
    out = []
    for day in pd.bdate_range(START, END):
        if day not in daily.index:
            continue
        k = dlist.index(day)
        if k < 60:
            continue
        prev = daily.iloc[:k]
        lv = {"pdh": prev.h.iloc[-1], "pdl": prev.l.iloc[-1]}
        mon = day - pd.Timedelta(days=day.dayofweek)
        pw = daily[(daily.index >= mon - pd.Timedelta(days=7)) & (daily.index < mon)]
        lv["pwh"], lv["pwl"] = (pw.h.max(), pw.l.min()) if len(pw) else (np.nan, np.nan)
        for n in (20, 40, 60):
            lv[f"h{n}"], lv[f"l{n}"] = prev.h.iloc[-n:].max(), prev.l.iloc[-n:].min()
        mid20 = (lv["h20"] + lv["l20"]) / 2
        d0 = pd.Timestamp(day).tz_localize(NYZ)
        ws_t, we_t = d0 + pd.Timedelta(hours=10), d0 + pd.Timedelta(hours=11)
        q = lambda t: int(np.searchsorted(ts, t.value))  # noqa: E731
        i_day, i_ph, ws, we = q(d0), q(ws_t - pd.Timedelta(minutes=60)), q(ws_t), q(we_t)
        i_exp, hard = q(we_t + pd.Timedelta(minutes=5)), q(we_t + pd.Timedelta(minutes=60)) - 1
        if not (ws > i_day and ws > i_ph and we > ws + 3 and hard >= we):
            continue
        px = df.mo.iat[ws]
        hb, lb = df.mh.iloc[i_day:ws].max(), df.ml.iloc[i_day:ws].min()
        cand = []
        for key, v in lv.items():
            hi = key.startswith(("pdh", "pwh", "h"))
            if pd.isna(v) or (hi and hb > v) or ((not hi) and lb < v):
                continue
            if (hi and v > px) or ((not hi) and v < px):
                cand.append((abs(v - px), v))
        if not cand:
            continue
        draw = min(cand)[1]
        side = 1 if draw > px else -1
        if side == 1:
            lvl = max(df.ml.iloc[i_day:ws].min(), df.ml.iloc[i_ph:ws].min())
            sw = next((x for x in range(ws, we) if df.ml.iat[x] < lvl), None)
        else:
            lvl = min(df.mh.iloc[i_day:ws].max(), df.mh.iloc[i_ph:ws].max())
            sw = next((x for x in range(ws, we) if df.mh.iat[x] > lvl), None)
        if sw is None:
            continue
        # SMT on partner bars [window start, sweep bar time]
        p_day, p_ph, p_ws = (int(np.searchsorted(pts, t.value)) for t in (d0, ws_t - pd.Timedelta(minutes=60), ws_t))
        p_end = int(np.searchsorted(pts, ts[sw], side="right"))
        if not (p_ws > p_day and p_ws > p_ph and p_end > p_ws):
            continue
        want_low = (side == 1) == (c["rel"] == 1)
        if want_low:
            plvl = max(pf.ml.iloc[p_day:p_ws].min(), pf.ml.iloc[p_ph:p_ws].min())
            if pf.ml.iloc[p_ws:p_end].min() < plvl:
                continue
        else:
            plvl = min(pf.mh.iloc[p_day:p_ws].max(), pf.mh.iloc[p_ph:p_ws].max())
            if pf.mh.iloc[p_ws:p_end].max() > plvl:
                continue
        ref_lvl = None
        for j in range(sw - 2, i_day, -1):
            if side == 1 and df.mh.iat[j] > df.mh.iat[j - 1] and df.mh.iat[j] > df.mh.iat[j + 1]:
                ref_lvl = df.mh.iat[j]
                break
            if side == -1 and df.ml.iat[j] < df.ml.iat[j - 1] and df.ml.iat[j] < df.ml.iat[j + 1]:
                ref_lvl = df.ml.iat[j]
                break
        if ref_lvl is None:
            continue
        mss = next((m for m in range(sw + 1, we) if (df.mc.iat[m] > ref_lvl if side == 1 else df.mc.iat[m] < ref_lvl)), None)
        if mss is None:
            continue
        setup = None
        for k3 in range(sw + 1, we):
            k2, k1 = k3 - 1, k3 - 2
            if k2 < sw or k2 > mss or pd.isna(df.atr.iat[k1]):
                continue
            top, bot = (df.ml.iat[k3], df.mh.iat[k1]) if side == 1 else (df.ml.iat[k1], df.mh.iat[k3])
            if top <= bot:
                continue
            rng = df.mh.iat[k2] - df.ml.iat[k2]
            if rng <= 0 or abs(df.mc.iat[k2] - df.mo.iat[k2]) / rng < 0.65 or rng < 1.5 * df.atr.iat[k1]:
                continue
            if top - bot < 2 * (df.ac.iat[k3] - df.bc.iat[k3]):
                continue
            last = max(k3, mss)
            lo, hi = df.ml.iloc[sw:last + 1].min(), df.mh.iloc[sw:last + 1].max()
            entry = hi - 0.705 * (hi - lo) if side == 1 else lo + 0.705 * (hi - lo)
            stop = lo - c["bmin"] if side == 1 else hi + c["bmin"]
            if (side == 1 and entry >= mid20) or (side == -1 and entry <= mid20):
                break
            dist = max((entry - stop) * side, c["bmin"])
            tpd = (draw - entry) * side
            if tpd < c["frame"] or tpd / dist < 2.0:
                break
            setup = (last, entry, entry - side * dist, draw, dist)
            break
        if setup is None:
            continue
        last, entry, sl, tp, dist = setup
        fill = next((x for x in range(last + 1, i_exp)
                     if (side == 1 and df.al.iat[x] <= entry) or (side == -1 and df.bh.iat[x] >= entry)), None)
        if fill is None:
            continue
        reason, epx = 3, (df.bc.iat[hard] if side == 1 else df.ac.iat[hard])
        for x in range(fill, hard + 1):
            if (side == 1 and df.bl.iat[x] <= sl) or (side == -1 and df.ah.iat[x] >= sl):
                reason, epx = 1, sl
                break
            if x > fill and ((side == 1 and df.bh.iat[x] >= tp) or (side == -1 and df.al.iat[x] <= tp)):
                reason, epx = 2, tp
                break
        slip = 0.0 if reason == 2 else c["slip"]
        epx = epx - slip if side == 1 else epx + slip
        out.append((day.date(), side, reason, round(entry, 8), round(sl, 8), ((epx - entry) * side - c["comm"]) / dist))
    return out


def run() -> int:
    ok_all = True
    for sym in ("USA30IDXUSD", "AUDUSD"):
        b = base.prepare(load_m1(sym))
        pb = base.prepare(load_m1(C[sym]["partner"]))
        days = base.day_table(b, "AM", START, END)
        m = main.run_slot_v5(b, days, sym, "AM", pb)
        a = [(pd.Timestamp(r.day).date(), int(r.side), int(r.reason), round(r.entry, 8), round(r.sl, 8), r.r)
             for r in m.itertuples()]
        r_ = ref(sym)
        same = len(a) == len(r_) and all(x[:5] == y[:5] for x, y in zip(a, r_, strict=False))
        dr = max((abs(x[5] - y[5]) for x, y in zip(a, r_, strict=False)), default=0.0)
        if not same:
            sa, sr = {x[:5] for x in a}, {y[:5] for y in r_}
            print("   only main:", sorted(sa - sr)[:4], "\n   only ref:", sorted(sr - sa)[:4])
        ok = bool(same and dr < 1e-9)
        ok_all &= ok
        print(f"{sym} AM 2018->end v5: main {len(a)} ref {len(r_)} keys_equal {same} max|dR| {dr:.2e} -> "
              f"{'MATCH' if ok else 'MISMATCH'}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(run())
