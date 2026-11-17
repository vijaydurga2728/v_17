"""Cycle 17 independent re-implementation check (Silver Bullet v2), written from the pre-reg text.

Shares only the M1 loader with the main engine. Compares trade by trade for NY AM on NAS100 and EURUSD (dev).
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

from run_c17_silver_bullet import load  # noqa: E402  (data loading only)
from v17.setups import c17_silver_bullet as main  # noqa: E402  (only to run the main engine for comparison)

# pre-reg §2 constants, typed independently
CONST = {"USATECHIDXUSD": dict(bmin=2.0, bmax=20.0, fb=15.0, slip=0.5, comm=0.0),
         "EURUSD": dict(bmin=0.0002, bmax=0.0015, fb=0.0020, slip=0.00005, comm=0.00006)}


def frame(sym: str) -> pd.DataFrame:
    b = load(sym)
    df = pd.DataFrame({"ts": b.ts, "bo": b.bid_o, "bh": b.bid_h, "bl": b.bid_l, "bc": b.bid_c,
                       "ao": b.ask_o, "ah": b.ask_h, "al": b.ask_l, "ac": b.ask_c})
    for k, (x, y) in {"o": ("bo", "ao"), "h": ("bh", "ah"), "l": ("bl", "al"), "c": ("bc", "ac")}.items():
        df["m" + k] = (df[x] + df[y]) / 2
    pc = df["mc"].shift(1)
    tr = pd.concat([df.mh - df.ml, (df.mh - pc).abs(), (df.ml - pc).abs()], axis=1).max(axis=1, skipna=True)
    tr[pc.isna()] = df.mh - df.ml
    df["atr"] = tr.rolling(14).mean()
    df["t"] = pd.to_datetime(df["ts"], unit="ns", utc=True).dt.tz_convert("America/New_York")
    return df.set_index("t", drop=False)


def ref_trades(df: pd.DataFrame, sym: str, start: str, end: str) -> list[tuple]:
    c = CONST[sym]
    out = []
    pos = pd.Series(np.arange(len(df)), index=df.index)
    for day in pd.bdate_range(start, end):
        d0 = pd.Timestamp(day).tz_localize("America/New_York")
        ws, we = d0 + pd.Timedelta(hours=10), d0 + pd.Timedelta(hours=11)
        pre = df[(df.t >= d0) & (df.t < ws)]
        ph = df[(df.t >= ws - pd.Timedelta(minutes=60)) & (df.t < ws)]
        win = df[(df.t >= ws) & (df.t < we)]
        hard_rows = df[df.t < we + pd.Timedelta(minutes=60)]
        if len(pre) == 0 or len(ph) == 0 or len(win) <= 3 or len(hard_rows) == 0 or hard_rows.t.iloc[-1] < we:
            continue
        hard_pos = int(pos.iloc[len(hard_rows) - 1])
        hi_pool = [pre.mh.max(), ph.mh.max()]
        lo_pool = [pre.ml.min(), ph.ml.min()]
        side, sw = 0, None
        for t, r in win.iterrows():
            lo = any(r.ml < p for p in lo_pool)
            hi = any(r.mh > p for p in hi_pool)
            if lo and hi:
                side = None
                break
            if lo or hi:
                side, sw = (1 if lo else -1), int(pos[t])
                break
        if not side:
            continue
        ext = df.ml.iat[sw] if side == 1 else df.mh.iat[sw]
        setup = None
        last = int(pos[win.t.iloc[-1]])
        for k3 in range(sw + 1, last + 1):
            ext = min(ext, df.ml.iat[k3]) if side == 1 else max(ext, df.mh.iat[k3])
            k2, k1 = k3 - 1, k3 - 2
            if k2 < sw or pd.isna(df.atr.iat[k1]):
                continue
            if side == 1:
                top, bot = df.ml.iat[k3], df.mh.iat[k1]
            else:
                top, bot = df.ml.iat[k1], df.mh.iat[k3]
            if top <= bot:
                continue
            body = abs(df.mc.iat[k2] - df.mo.iat[k2])
            rng = df.mh.iat[k2] - df.ml.iat[k2]
            if rng <= 0 or body / rng < 0.65 or rng < 1.5 * df.atr.iat[k1]:
                continue
            if top - bot < 2 * (df.ac.iat[k3] - df.bc.iat[k3]):
                continue
            ce = (top + bot) / 2
            if side == 1:
                dist = ce - (ext - c["bmin"])
                tgt = [p for p in hi_pool if p > ce]
                tp = min(tgt) if tgt else ce + c["fb"]
            else:
                dist = (ext + c["bmin"]) - ce
                tgt = [p for p in lo_pool if p < ce]
                tp = max(tgt) if tgt else ce - c["fb"]
            if dist > c["bmax"]:
                continue
            dist = max(dist, c["bmin"])
            if abs(tp - ce) / dist < 1.5:
                continue
            setup = (k3, ce, ce - side * dist, tp, dist)
            break
        if setup is None:
            continue
        k3, ce, sl, tp, dist = setup
        exp_rows = df[df.t < we + pd.Timedelta(minutes=5)]
        fill = None
        for k in range(k3 + 1, len(exp_rows)):
            if (side == 1 and df.al.iat[k] <= ce) or (side == -1 and df.bh.iat[k] >= ce):
                fill = k
                break
        if fill is None:
            continue
        reason, px, xk = 3, (df.bc.iat[hard_pos] if side == 1 else df.ac.iat[hard_pos]), hard_pos
        for k in range(fill, hard_pos + 1):
            if side == 1:
                if df.bl.iat[k] <= sl:
                    reason, px, xk = 1, sl, k
                    break
                if k > fill and df.bh.iat[k] >= tp:
                    reason, px, xk = 2, tp, k
                    break
            else:
                if df.ah.iat[k] >= sl:
                    reason, px, xk = 1, sl, k
                    break
                if k > fill and df.al.iat[k] <= tp:
                    reason, px, xk = 2, tp, k
                    break
        slip = 0.0 if reason == 2 else c["slip"]
        px = px - slip if side == 1 else px + slip
        r = ((px - ce) * side - c["comm"]) / dist
        out.append((day.date(), side, int(fill), int(xk), reason, round(ce, 8), r))
    return out


def run() -> int:
    ok_all = True
    for sym in ("USATECHIDXUSD", "EURUSD"):
        df = frame(sym)
        b = load(sym)
        days = main.day_table(b, "AM", "2018-01-01", "2024-12-31")
        m = main.run_slot(b, days, main.SPECS[sym])
        a = [(pd.Timestamp(r.day).date(), int(r.side), int(r.fill_i), int(r.exit_i), int(r.reason), round(r.entry, 8), r.r)
             for r in m.itertuples()]
        b_ = ref_trades(df, sym, "2018-01-01", "2024-12-31")
        same_n = len(a) == len(b_)
        keys = same_n and all(x[:6] == y[:6] for x, y in zip(a, b_, strict=True))
        dr = max((abs(x[6] - y[6]) for x, y in zip(a, b_, strict=True)), default=0.0) if same_n else None
        if not keys:
            sa, sb_ = set(x[:6] for x in a), set(y[:6] for y in b_)
            print("   only in main:", sorted(sa - sb_)[:5], "\n   only in ref:", sorted(sb_ - sa)[:5])
        ok = bool(keys and dr is not None and dr < 1e-9)
        ok_all &= ok
        print(f"{sym} AM: main {len(a)} ref {len(b_)} keys_equal {keys} max|dR| {dr} -> {'MATCH' if ok else 'MISMATCH'}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(run())
