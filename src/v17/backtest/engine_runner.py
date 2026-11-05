"""Per-engine OOS runner — full context assembly (Task 5.3).

Wires D1 bias, ATR_14 rolling, SpreadGuard, liquidity pools,
sweep-confirmation, displacement + FVG detection, and compute_sl_tp
so trades fire with real SL/TP/R:R.

Public API preserved:
  - TradeLog dataclass
  - run_engine_oos(config, bars, calendar, fold) -> TradeLog
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, timezone
from typing import Optional

import numpy as np
import pandas as pd

from v17.backtest.walkforward import Fold
from v17.data.calendar.blackout import is_in_blackout, SYMBOL_CURRENCY_MAP
from v17.data.spread_guard import SpreadGuard
from v17.setups.sb_constants import (
    ATR_PERIOD_M1,
    STRUCTURAL_FALLBACK_FX_PIPS,
    STRUCTURAL_FALLBACK_USATECH_PTS,
)
from v17.setups.sb_engines import SBEngineConfig
from v17.setups.sb_sl_tp import compute_sl_tp, SBRejectError
from v17.setups.silver_bullet_fsm import SilverBulletFSM, SBSignal
from v17.structure.bias import compute_d1_bias
from v17.structure.displacement import is_displacement
from v17.structure.fvg_sb import detect_fvgs_at
from v17.structure.liquidity_pools import enumerate_pools
from v17.common.instrument_spec import pip_size

_NS_PER_MIN: int = 60_000_000_000
_NS_PER_DAY: int = 86_400_000_000_000


@dataclass
class TradeLog:
    engine_id: str
    fold_id: int
    trades: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _window_ns(ny_date: date, window_ny: tuple[str, str]) -> tuple[int, int]:
    """Convert a NY-local (HH:MM, HH:MM) pair on a given NY date to UTC ns."""
    import pytz
    tz = pytz.timezone("America/New_York")
    start_h, start_m = int(window_ny[0][:2]), int(window_ny[0][3:])
    end_h, end_m = int(window_ny[1][:2]), int(window_ny[1][3:])
    from datetime import datetime
    start_naive = datetime(ny_date.year, ny_date.month, ny_date.day, start_h, start_m)
    end_naive = datetime(ny_date.year, ny_date.month, ny_date.day, end_h, end_m)
    start_aware = tz.localize(start_naive)
    end_aware = tz.localize(end_naive)
    start_ns = int(start_aware.timestamp() * 1e9)
    end_ns = int(end_aware.timestamp() * 1e9)
    return start_ns, end_ns


def _build_d1_bars(sym_bars: pd.DataFrame) -> pd.DataFrame:
    """Resample M1 bars to daily bars, one per NY calendar date.

    ts_utc is set to the actual ts_utc of the last M1 bar in the NY session
    so that causality checks in compute_d1_bias (which filter
    d1_bars[d1_bars["ts_utc"] < as_of_utc_ns]) correctly exclude any D1 bar
    whose session has not fully closed before as_of_utc_ns.

    bid_c / ask_c = last M1 close of the NY session.
    """
    df = sym_bars.copy()
    ny_dates = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.date
    df["_ny_date"] = ny_dates
    grp = df.groupby("_ny_date")
    rows = []
    for d, g in grp:
        g = g.sort_values("ts_utc")
        last_ts_ns = int(g["ts_utc"].iloc[-1])
        rows.append(
            {
                "ts_utc": last_ts_ns,
                "bid_c": float(g["bid_c"].iloc[-1]),
                "ask_c": float(g["ask_c"].iloc[-1]),
            }
        )
    return pd.DataFrame(rows).sort_values("ts_utc").reset_index(drop=True)


def _compute_atr14(sym_bars: pd.DataFrame) -> pd.Series:
    """Wilder-approximated ATR_14 on bid OHLC, indexed by sym_bars.index."""
    h = sym_bars["bid_h"].to_numpy(dtype=float)
    l = sym_bars["bid_l"].to_numpy(dtype=float)
    c = sym_bars["bid_c"].to_numpy(dtype=float)
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    # Simple rolling mean as Wilder approximation (matches brief spec)
    atr = pd.Series(tr, index=sym_bars.index).rolling(ATR_PERIOD_M1, min_periods=ATR_PERIOD_M1).mean()
    return atr


def _opposing_target(
    side: str,
    entry: float,
    pools: list[dict],
    symbol: str,
) -> float:
    """Return the structural opposing target per SB-05.

    LONG: highest pool price (session_high or prev_hour_high) strictly above entry.
    SHORT: lowest pool price (session_low or prev_hour_low) strictly below entry.
    Fallback to entry +/- structural fallback when no pool qualifies or R:R would fail.
    """
    pip = pip_size(symbol)
    is_index = symbol in {"USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD"}

    if side == "LONG":
        candidates = [
            p["price"]
            for p in pools
            if p["kind"].endswith("_high") and p["price"] > entry
        ]
        if candidates:
            return max(candidates)
        fallback_dist = (
            STRUCTURAL_FALLBACK_USATECH_PTS if is_index
            else STRUCTURAL_FALLBACK_FX_PIPS * pip
        )
        return entry + fallback_dist
    else:  # SHORT
        candidates = [
            p["price"]
            for p in pools
            if p["kind"].endswith("_low") and p["price"] < entry
        ]
        if candidates:
            return min(candidates)
        fallback_dist = (
            STRUCTURAL_FALLBACK_USATECH_PTS if is_index
            else STRUCTURAL_FALLBACK_FX_PIPS * pip
        )
        return entry - fallback_dist


# ---------------------------------------------------------------------------
# main runner
# ---------------------------------------------------------------------------

def run_engine_oos(
    config: SBEngineConfig,
    bars: pd.DataFrame,
    calendar: pd.DataFrame,
    fold: Fold,
) -> TradeLog:
    """Execute one engine over one fold's OOS window across its eligible symbols.

    Full context assembly: D1 bias, ATR_14, SpreadGuard, blackout gate,
    liquidity pools, sweep confirmation, displacement + FVG detection,
    compute_sl_tp. SBSignal.sl_price / tp_price / r_multiple are filled.
    """
    log = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
    fsm = SilverBulletFSM(config)

    for symbol in config.symbols:
        # All bars for this symbol (full history for SpreadGuard / D1 bias)
        all_sym = bars[bars["symbol"] == symbol].copy()
        if all_sym.empty:
            continue

        # OOS slice only
        oos_mask = (all_sym["ts_utc"] >= fold.oos_start) & (all_sym["ts_utc"] < fold.oos_end)
        oos_bars = all_sym[oos_mask].copy().reset_index(drop=True)
        if oos_bars.empty:
            continue

        # SpreadGuard: full history so 30-day lookback works from day 1 of OOS
        spread_guard = SpreadGuard(all_sym, symbol)

        # D1 bars: built from full history (prior days + OOS) for bias computation
        d1_bars = _build_d1_bars(all_sym)

        # ATR_14: computed on the OOS slice (brief says "sliced to OOS")
        atr_series = _compute_atr14(oos_bars)

        # Calendar currencies for blackout check
        currencies = SYMBOL_CURRENCY_MAP.get(symbol, [])

        # Determine which NY dates are covered by OOS bars
        oos_ts = pd.to_datetime(oos_bars["ts_utc"], utc=True)
        ny_dates: list[date] = sorted(
            set(oos_ts.dt.tz_convert("America/New_York").dt.date.tolist())
        )

        # Build a fast index: ts_utc -> row position in oos_bars
        ts_to_idx: dict[int, int] = {
            int(oos_bars.at[i, "ts_utc"]): i for i in range(len(oos_bars))
        }

        # Track which (symbol, day) already fired a trade on this engine
        fired_days: set[date] = set()

        for ny_date in ny_dates:
            if ny_date in fired_days:
                continue

            window_start_ns, window_end_ns = _window_ns(ny_date, config.window_ny)

            # D1 bias: computed as of window_start_ns (causal, same-day uses prior bars)
            d1_bias = compute_d1_bias(d1_bars, as_of_utc_ns=window_start_ns)
            if d1_bias == "NONE":
                continue

            # Day mask in oos_bars: bars in [window_start_ns, window_end_ns)
            window_mask = (
                (oos_bars["ts_utc"] >= window_start_ns)
                & (oos_bars["ts_utc"] < window_end_ns)
            )
            day_window_bars = oos_bars[window_mask]
            if day_window_bars.empty:
                continue

            # Per-day sweep state
            sweep_confirmed = False
            sweep_extreme: Optional[float] = None
            swept_pool_kind: Optional[str] = None
            displacement_bar_fvg: Optional[dict] = None

            for local_i, row in day_window_bars.iterrows():
                bar_ts = int(row["ts_utc"])
                bar = row.to_dict()

                # Hard exit: no entries at or beyond window_end
                if bar_ts >= window_end_ns:
                    break

                # ATR check
                atr_14 = float(atr_series.at[local_i]) if local_i in atr_series.index else float("nan")
                if np.isnan(atr_14) or atr_14 <= 0:
                    continue

                # Blackout gate
                if is_in_blackout(bar_ts, calendar, currencies):
                    continue

                # Spread guard
                current_spread = float(bar.get("spread_mid", 0.0))
                if spread_guard.should_reject(bar_ts, current_spread):
                    continue

                # Enumerate liquidity pools (pre-window context up to current bar)
                pools = enumerate_pools(
                    all_sym, window_start_ns=window_start_ns, now_ns=bar_ts + 1
                )

                # Sweep confirmation (running state)
                if not sweep_confirmed:
                    if d1_bias == "BULLISH":
                        low_pools = [p for p in pools if p["kind"].endswith("_low")]
                        for p in low_pools:
                            if float(row["bid_l"]) < p["price"]:
                                sweep_confirmed = True
                                swept_pool_kind = p["kind"]
                                sweep_extreme = float(row["bid_l"])
                                break
                    else:  # BEARISH
                        high_pools = [p for p in pools if p["kind"].endswith("_high")]
                        for p in high_pools:
                            if float(row["bid_h"]) > p["price"]:
                                sweep_confirmed = True
                                swept_pool_kind = p["kind"]
                                sweep_extreme = float(row["bid_h"])
                                break

                if not sweep_confirmed:
                    continue

                # Update sweep extreme with running min/max
                if d1_bias == "BULLISH" and sweep_extreme is not None:
                    sweep_extreme = min(sweep_extreme, float(row["bid_l"]))
                elif d1_bias == "BEARISH" and sweep_extreme is not None:
                    sweep_extreme = max(sweep_extreme, float(row["bid_h"]))

                # Displacement + FVG detection
                # as_of_ns = bar_ts + 60s so bar i is fully "printed"
                as_of_ns = bar_ts + _NS_PER_MIN
                fvgs = detect_fvgs_at(all_sym, as_of_ns=as_of_ns)

                # Pick latest FVG matching bias whose ts_ns == bar_ts (displacement bar == bar i)
                expected_kind = "bullish" if d1_bias == "BULLISH" else "bearish"
                matching = [
                    f for f in fvgs
                    if f["kind"] == expected_kind and f["ts_ns"] == bar_ts
                ]
                if matching and is_displacement(bar, atr_14):
                    displacement_bar_fvg = matching[-1]

                if displacement_bar_fvg is None:
                    continue

                # Build context for FSM
                context = {
                    "d1_bias": d1_bias,
                    "atr_14": atr_14,
                    "spread": current_spread,
                    "spread_median": 0.0,  # FSM uses spread guard separately; pass 0 to skip FSM dupe check
                    "calendar_blackout": False,  # already gated above
                    "window_open": True,
                    "liquidity_pools": pools,
                    "fvgs": fvgs,
                    "sweep_confirmed": sweep_confirmed,
                    "swept_pool_kind": swept_pool_kind,
                    "displacement_bar_fvg": displacement_bar_fvg,
                }

                # CE fill check: for CE model, fill when CE is inside bar's bid range
                # FSM.step will check entry model and return signal if gates pass
                sig: Optional[SBSignal] = fsm.step(bar, context)
                if sig is None:
                    continue

                # For CE model: verify fill condition (CE inside this bar's range)
                if config.entry_model == "CE":
                    ce = sig.entry_price
                    if not (float(row["bid_l"]) <= ce <= float(row["bid_h"])):
                        continue
                else:  # AGGRESSIVE: fill at top (LONG) or bottom (SHORT)
                    target_edge = sig.entry_price
                    if not (float(row["bid_l"]) <= target_edge <= float(row["bid_h"])):
                        continue

                # SL/TP replacement via compute_sl_tp
                if sweep_extreme is None:
                    continue
                opposing = _opposing_target(sig.side, sig.entry_price, pools, symbol)
                try:
                    sltp = compute_sl_tp(
                        side=sig.side,
                        entry=sig.entry_price,
                        sweep_extreme=sweep_extreme,
                        opposing_target=opposing,
                        symbol=symbol,
                    )
                except SBRejectError:
                    continue

                # Freeze-replace sentinel SBSignal with real SL/TP
                sig = dataclasses.replace(
                    sig,
                    sl_price=sltp.sl,
                    tp_price=sltp.tp,
                    r_multiple=sltp.r_multiple,
                )

                log.trades.append(sig)
                fired_days.add(ny_date)
                break  # hard exit: one trade per (symbol, day, engine)

    return log
