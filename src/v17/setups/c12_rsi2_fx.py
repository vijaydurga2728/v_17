"""Cycle 12 — RSI(2) on FX majors (pre-reg d8bd7fd).

NY-17:00 D1 bars, long-only (L) and symmetric (S) variants, bid/ask fills, and a
precomputed per-bar outcome table used by both the engine and the random-entry
luck test (each trade's exit depends only on its own entry bar).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from v17.backtest.rsi2_runner import _rsi_wilder, _sma
from v17.setups.rsi2_constants import (
    LONG_THRESHOLD,
    RSI_PERIOD_D1,
    SMA_EXIT_PERIOD_D1,
    TIME_CAP_D1,
)

PAIRS: Final[tuple[str, ...]] = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD")
VARIANTS: Final[tuple[str, ...]] = ("L", "S")
SHORT_THRESHOLD: Final[float] = 100.0 - LONG_THRESHOLD  # RSI(2) > 90
R_UNIT_FRAC: Final[float] = 0.01
RUNNER_SLIPPAGE: Final[float] = 0.5  # parity mode only (cycle 4B NAS100 points)
PX: Final[tuple[str, ...]] = ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c")


def slots() -> list[tuple[str, str]]:
    return [(p, v) for p in PAIRS for v in VARIANTS]


def build_fxny_d1(m1: pd.DataFrame) -> pd.DataFrame:
    """D1 bars on the 17:00 America/New_York rollover, labelled by closing day; Mon-Fri only."""
    m1 = m1.sort_values("ts_utc", kind="mergesort")
    ny = (pd.to_datetime(m1["ts_utc"].to_numpy(dtype=np.int64), unit="ns", utc=True)
          .tz_convert("America/New_York").tz_localize(None))
    day = (ny + pd.Timedelta(hours=7)).normalize()
    df = m1[["ts_utc", *PX]].copy()
    df["day"] = day.to_numpy()
    g = df.groupby("day", sort=True)
    out = pd.DataFrame({
        "ts_utc": g["ts_utc"].last(),
        "bid_o": g["bid_o"].first(), "bid_h": g["bid_h"].max(),
        "bid_l": g["bid_l"].min(), "bid_c": g["bid_c"].last(),
        "ask_o": g["ask_o"].first(), "ask_h": g["ask_h"].max(),
        "ask_l": g["ask_l"].min(), "ask_c": g["ask_c"].last(),
        "n_m1": g["ts_utc"].count(),
    }).reset_index()
    out = out[pd.to_datetime(out["day"]).dt.dayofweek < 5].reset_index(drop=True)
    return out


@dataclass
class Prepared:
    d1: pd.DataFrame
    day_ns: np.ndarray       # bar label (closing NY day) as int64 ns
    mid_c: np.ndarray
    rsi: np.ndarray
    sma: np.ndarray


def prepare(d1: pd.DataFrame) -> Prepared:
    mid_c = ((d1["bid_c"] + d1["ask_c"]) / 2).to_numpy(dtype=np.float64)
    return Prepared(d1.reset_index(drop=True),
                    pd.to_datetime(d1["day"]).to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    mid_c, _rsi_wilder(mid_c, RSI_PERIOD_D1), _sma(mid_c, SMA_EXIT_PERIOD_D1))


def _outcome(p: Prepared, i: int, side: int, win_end_ns: int, fill: str) -> tuple[int, float, float]:
    """Trade from signal bar i. Returns (exit_bar, R, entry-bar spread in R)."""
    d = p.d1
    n = len(p.mid_c)
    e = i + 1
    r_unit = R_UNIT_FRAC * p.mid_c[i] if fill == "bidask" else max(p.mid_c[i] * R_UNIT_FRAC, 1e-9)
    x = None
    for j in range(e, min(e + TIME_CAP_D1 + 1, n)):
        if p.day_ns[j] >= win_end_ns:
            x = j
            break
        if np.isfinite(p.sma[j]) and (p.mid_c[j] > p.sma[j] if side == 1 else p.mid_c[j] < p.sma[j]):
            x = j
            break
    if x is None:
        x = min(e + TIME_CAP_D1, n - 1)
    if fill == "runner":  # cycle 4B: mid open + slippage, mid close exit, long only
        mid_o = (d.at[e, "bid_o"] + d.at[e, "ask_o"]) / 2
        return x, (p.mid_c[x] - (mid_o + RUNNER_SLIPPAGE)) / r_unit, 0.0
    spread_r = (d.at[e, "ask_o"] - d.at[e, "bid_o"]) / r_unit
    if side == 1:
        return x, (d.at[x, "bid_c"] - d.at[e, "ask_o"]) / r_unit, spread_r
    return x, (d.at[e, "bid_o"] - d.at[x, "ask_c"]) / r_unit, spread_r


def signal_side(p: Prepared, i: int, variant: str) -> int:
    r = p.rsi[i]
    if not np.isfinite(r):
        return 0
    if r < LONG_THRESHOLD:
        return 1
    if variant == "S" and r > SHORT_THRESHOLD:
        return -1
    return 0


def run(p: Prepared, variant: str, win_start_ns: int, win_end_ns: int,
        fill: str = "bidask") -> pd.DataFrame:
    """Sequential engine (one position at a time), cycle 4B loop semantics."""
    n = len(p.mid_c)
    rows = []
    i = max(RSI_PERIOD_D1 + 1, SMA_EXIT_PERIOD_D1)
    while i < n - 1:
        if p.day_ns[i] < win_start_ns:
            i += 1
            continue
        if p.day_ns[i] >= win_end_ns:
            break
        side = signal_side(p, i, variant)
        if side == 0:
            i += 1
            continue
        x, r, spread_r = _outcome(p, i, side, win_end_ns, fill)
        rows.append({"signal_i": i, "entry_i": i + 1, "exit_i": x, "side": side,
                     "ts_entry_ns": int(p.day_ns[i + 1]), "pnl_r": r, "spread_r": spread_r,
                     "fold_id": int(pd.Timestamp(int(p.day_ns[i + 1])).year)})
        i = x + 1
    return pd.DataFrame(rows, columns=["signal_i", "entry_i", "exit_i", "side", "ts_entry_ns",
                                       "pnl_r", "spread_r", "fold_id"])


def outcome_table(p: Prepared, win_start_ns: int, win_end_ns: int) -> pd.DataFrame:
    """R of a long and a short trade from every eligible signal bar in the window (luck-test pool)."""
    n = len(p.mid_c)
    lo = max(RSI_PERIOD_D1 + 1, SMA_EXIT_PERIOD_D1)
    idx = [i for i in range(lo, n - 1) if win_start_ns <= p.day_ns[i] < win_end_ns]
    rl = [_outcome(p, i, 1, win_end_ns, "bidask")[1] for i in idx]
    rs = [_outcome(p, i, -1, win_end_ns, "bidask")[1] for i in idx]
    return pd.DataFrame({"signal_i": idx, "r_long": rl, "r_short": rs})


def luck_test(trades: pd.DataFrame, pool: pd.DataFrame, seed: int,
              n_perms: int = 10_000) -> dict[str, float]:
    n_long = int((trades["side"] == 1).sum())
    n_short = int((trades["side"] == -1).sum())
    k = n_long + n_short
    if k == 0 or k > len(pool):
        raise ValueError(f"cannot draw {k} entries from pool of {len(pool)}")
    rl, rs = pool["r_long"].to_numpy(), pool["r_short"].to_numpy()
    observed = float(trades["pnl_r"].mean())
    null = np.empty(n_perms)
    for j in range(n_perms):
        pick = np.random.default_rng([seed, j]).choice(len(pool), size=k, replace=False)
        null[j] = (rl[pick[:n_long]].sum() + rs[pick[n_long:]].sum()) / k
    e = int((null >= observed).sum())
    return {"observed_mean_r": observed, "null_mean_r_median": float(np.median(null)),
            "exceedances": e, "n_perms": n_perms, "p_mean_r": (e + 1) / (n_perms + 1)}
