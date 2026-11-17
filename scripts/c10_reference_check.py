"""Cycle 10 independent reimplementation check (pre-reg §11.2).

A separate per-day implementation written from the pre-reg text, sharing no
strategy code with src/v17/setups/c10_intraday_momentum.py (only the dev M1
loader and the XNYS calendar). It must match the main implementation trade by
trade on dev before any Tier 1 result is reported. Prints only match statistics.

Usage: .venv/Scripts/python.exe scripts/c10_reference_check.py
"""
# ruff: noqa: B023, PLR0912, PLR0915, E501, PLR1714
# Deliberately plain per-day reference code: closures are called within the same loop
# iteration (B023 false positive); kept unrefactored so it stays independent of src/.
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.c9_runner import load_m1
from v17.setups import c10_intraday_momentum as main
from v17.setups.c9_pdh_pdl import DEV_END, DEV_START, full_rth_days


def ref_days(m1: pd.DataFrame) -> tuple[list, dict]:
    full = set(full_rth_days(DEV_START, DEV_END).astype("datetime64[D]").astype(object))
    t = pd.to_datetime(m1["ts_utc"], unit="ns", utc=True).dt.tz_convert("America/New_York")
    df = m1.assign(day=t.dt.date, mins=t.dt.hour * 60 + t.dt.minute - 570)
    df = df[df["day"].isin(full) & (df["mins"] >= 0) & (df["mins"] < 390)]
    for k in "ohlc":
        df[f"m{k}"] = (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2
    df["v"] = df["bid_volume"] + df["ask_volume"]
    days = {d: g.set_index("mins") for d, g in df.groupby("day")}
    return sorted(days), days


def ref_run(order: list, days: dict, slot: str, slip: float = 0.0) -> list[tuple]:
    cal = sorted(full_rth_days(DEV_START, DEV_END).astype("datetime64[D]").astype(object))
    pos_in_cal = {d: i for i, d in enumerate(cal)}

    def at(g: pd.DataFrame, i: int, col: str) -> float:
        return float(g.at[i, col]) if i in g.index else float("nan")

    oc = [abs(at(days[d], 389, "mc") / at(days[d], 0, "mo") - 1) for d in order]
    out = []
    for n, d in enumerate(order):
        g = days[d]
        if n == 0 or pos_in_cal[order[n - 1]] != pos_in_cal[d] - 1:
            continue
        pc = at(days[order[n - 1]], 389, "mc")
        if n < 14:
            continue
        ru = float(np.mean(oc[n - 14:n]))
        if not (np.isfinite(pc) and np.isfinite(ru)):
            continue

        def r_of(side: int, ei: int, xi: int) -> float:
            if side == 1:
                ep = at(g, ei, "ask_o") + slip
                xp = (at(g, 389, "bid_c") if xi == 390 else at(g, xi, "bid_o")) - slip
                return (xp - ep) / (ep * ru)
            ep = at(g, ei, "bid_o") - slip
            xp = (at(g, 389, "ask_c") if xi == 390 else at(g, xi, "ask_o")) + slip
            return (ep - xp) / (ep * ru)

        if slot in ("G", "B"):
            si = 29 if slot == "G" else 359
            s = at(g, si, "mc") / pc - 1
            need = [at(g, 360, "ask_o"), at(g, 360, "bid_o"), at(g, 389, "ask_c"), at(g, 389, "bid_c")]
            if not np.isfinite(s) or s == 0 or not all(np.isfinite(need)):
                continue
            side = 1 if s > 0 else -1
            out.append((d, side, 360, 390, r_of(side, 360, 390)))
            continue
        # slot Z
        prev14 = [days[order[n - k]] for k in range(1, 15)]
        o = at(g, 0, "mo")
        checks = list(range(29, 360, 30))
        if not all(np.isfinite(at(g, c, "mc")) and np.isfinite(at(g, c + 1, "ask_o"))
                   and np.isfinite(at(g, c + 1, "bid_o")) for c in checks):
            continue
        if not (np.isfinite(at(g, 389, "bid_c")) and np.isfinite(at(g, 389, "ask_c"))):
            continue
        tp = (g["mh"] + g["ml"] + g["mc"]) / 3
        cum_v = g["v"].cumsum()
        cum_pv = (tp * g["v"]).cumsum()
        pos = entry = 0
        for c in checks:
            mv = [abs(at(p, c, "mc") / at(p, 0, "mo") - 1) for p in prev14]
            mv = [x for x in mv if np.isfinite(x)]
            sig = 0
            if len(mv) >= 13 and cum_v.loc[:c].iloc[-1] > 0:
                sigma = float(np.mean(mv))
                vw = cum_pv.loc[:c].iloc[-1] / cum_v.loc[:c].iloc[-1]
                px = at(g, c, "mc")
                if px > max(o, pc) * (1 + sigma) and px > vw:
                    sig = 1
                elif px < min(o, pc) * (1 - sigma) and px < vw:
                    sig = -1
            if pos != 0 and sig != pos:
                out.append((d, pos, entry, c + 1, r_of(pos, entry, c + 1)))
                pos = 0
            if pos == 0 and sig != 0:
                pos, entry = sig, c + 1
        if pos != 0:
            out.append((d, pos, entry, 390, r_of(pos, entry, 390)))
    return out


def main_run(g: main.DayGrid, slot: str) -> list[tuple]:
    tr = main.run_slot(g, slot)
    dates = g.dates[tr.day].astype(object)
    return list(zip(dates, tr.side.tolist(), tr.entry_i.tolist(), tr.exit_i.tolist(),
                    tr.r.tolist(), strict=True))


def main_cli() -> int:
    m1 = load_m1("dev")
    g = main.build_grid(m1, DEV_START, DEV_END)
    order, days = ref_days(m1)
    ok_all = True
    for slot in main.SLOTS:
        a, b = main_run(g, slot), ref_run(order, days, slot)
        same_n = len(a) == len(b)
        keys_eq = same_n and all(x[:4] == y[:4] for x, y in zip(a, b, strict=True))
        dr = max((abs(x[4] - y[4]) for x, y in zip(a, b, strict=True)), default=0.0) if same_n else None
        ok = bool(keys_eq and dr is not None and dr < 1e-9)
        ok_all &= ok
        print(f"{slot}: main {len(a)} ref {len(b)} keys_equal {keys_eq} max|dR| {dr} -> {'MATCH' if ok else 'MISMATCH'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main_cli())
