"""INDEPENDENT reference implementation of cycle 9, written from the spec text only.
Shares NO code with src/v17/setups/c9_pdh_pdl.py except the raw M1 loader + calendar lib.
pre-reg §5-11 + ADR 001 B-F + IMPL-3/4/6/8 (approved)."""
import numpy as np, pandas as pd, pandas_market_calendars as pmc

def m15_from_m1(m1):
    sch = pmc.get_calendar("XNYS").schedule("2015-01-01", "2022-12-31")
    full = sch[(sch.market_close - sch.market_open) == pd.Timedelta("6h30m")]
    fulldays = set(full.index.date)
    t = pd.to_datetime(m1.ts_utc, unit="ns", utc=True).dt.tz_convert("America/New_York")
    df = m1.assign(t=t, day=t.dt.date)
    df = df[df.day.isin(fulldays)]
    hm = df.t.dt.hour * 60 + df.t.dt.minute
    df = df[(hm >= 570) & (hm < 945)].copy()
    df["slot"] = df.t.dt.floor("15min")
    agg = df.sort_values("ts_utc").groupby("slot").agg(
        bid_o=("bid_o", "first"), bid_h=("bid_h", "max"), bid_l=("bid_l", "min"), bid_c=("bid_c", "last"),
        ask_o=("ask_o", "first"), ask_h=("ask_h", "max"), ask_l=("ask_l", "min"), ask_c=("ask_c", "last"),
        n=("ts_utc", "size"), day=("day", "first"))
    agg = agg[agg.n >= 5].copy()
    for k in "ohlc":
        agg["m" + k] = (agg["bid_" + k] + agg["ask_" + k]) / 2
    agg["is_last"] = (agg.index.hour == 15) & (agg.index.minute == 30)
    return agg, sorted(fulldays)

def wilder_atr_prev(h, l, c):
    tr = [np.nan] + [max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1])) for i in range(1, len(c))]
    atr = [np.nan] * len(c); prev = [np.nan] * len(c)
    if len(c) > 15:
        atr[14] = float(np.mean(tr[1:15]))
        for i in range(15, len(c)): atr[i] = (atr[i-1] * 13 + tr[i]) / 14
        for i in range(1, len(c)): prev[i] = atr[i-1]
    return prev

def run(agg, fulldays, buf, side, nconf, slip=0.0):
    bars = agg.reset_index()
    bars["atrp"] = wilder_atr_prev(bars.mh.tolist(), bars.ml.tolist(), bars.mc.tolist())
    days = {d: g for d, g in bars.groupby("day")}
    order = sorted(days)
    trades = []
    for di, d in enumerate(order):
        if di == 0: continue
        prevd = order[di - 1]
        if fulldays.index(prevd) != fulldays.index(d) - 1: continue   # IMPL-1
        P = days[prevd]; pdh, pdl = P.mh.max(), P.ml.min()
        g = days[d].reset_index(drop=True)
        if not g.is_last.iloc[-1]: continue                            # IMPL-8
        n = len(g); i = 0; entry = None
        while i < n:
            r = g.iloc[i]
            is_sweep = (r.ml < pdl and r.mc > pdl) if side == "long" else (r.mh > pdh and r.mc < pdh)
            if not (is_sweep and np.isfinite(r.atrp)):
                i += 1; continue
            k = i; conf = None
            for j in range(k + 1, min(k + nconf, n - 1) + 1):
                cj = g.mc.iloc[j]
                if (side == "long" and cj > g.mh.iloc[k]) or (side == "short" and cj < g.ml.iloc[k]):
                    conf = j; break
            if conf is None:
                i = k + nconf + 1; continue                            # IMPL-3
            if conf + 1 >= n: break
            entry = (k, conf); break
        if entry is None: continue
        k, j = entry; e = j + 1
        if side == "long":
            ep = g.ask_o.iloc[e] + slip; stop = g.ml.iloc[k] - buf * g.atrp.iloc[k]; tgt = pdh
        else:
            ep = g.bid_o.iloc[e] - slip; stop = g.mh.iloc[k] + buf * g.atrp.iloc[k]; tgt = pdl
        sd = abs(ep - stop)
        if sd <= 0: continue
        for x in range(e, n):
            b = g.iloc[x]
            if side == "long":
                o, hi, lo, cl = b.bid_o, b.bid_h, b.bid_l, b.bid_c
                if o <= stop: xp, why = o - slip, "stop_gap"
                elif o >= tgt: xp, why = o - slip, "target_gap"
                elif lo <= stop: xp, why = stop - slip, "stop"
                elif hi >= tgt: xp, why = tgt - slip, "target"
                elif x == n - 1: xp, why = cl - slip, "eod"
                else: continue
                R = (xp - ep) / sd
            else:
                o, hi, lo, cl = b.ask_o, b.ask_h, b.ask_l, b.ask_c
                if o >= stop: xp, why = o + slip, "stop_gap"
                elif o <= tgt: xp, why = o + slip, "target_gap"
                elif hi >= stop: xp, why = stop + slip, "stop"
                elif lo <= tgt: xp, why = tgt + slip, "target"
                elif x == n - 1: xp, why = cl + slip, "eod"
                else: continue
                R = (ep - xp) / sd
            trades.append(dict(date=d, entry_px=ep, exit_px=xp, exit_reason=why, r=R)); break
    return pd.DataFrame(trades)
