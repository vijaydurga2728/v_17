"""Cycle 6 backtest orchestrator."""
from __future__ import annotations

import uuid
from typing import Mapping

import numpy as np
import pandas as pd

from v17.backtest.c6_breakers import DailyState, allow_entry, evaluate, update_after_trade
from v17.backtest.c6_position import C6Position, step as position_step
from v17.backtest.c6_sizing import size_position
from v17.data.c6_calendar import is_blackout, is_calendar_stale
from v17.setups.c6_constants import (
    ATR_FLOOR_MULT, ATR_PERIOD, ENTRY_WINDOW_END_UTC_HM, ENTRY_WINDOW_START_UTC_HM,
    HARD_FLAT_HOUR_MIN_UTC, NEWS_BLACKOUT_MIN, NY_OPEN_BLACKOUT_UTC_HM,
    PORTFOLIO_RISK_PCT, RISK_PCT, SESSION_ANCHOR_HOUR_UTC, TRAIL_EMA_PERIOD, WARMUP_SPX_BARS,
)
from v17.setups.c6_engines import C6_CATALOG
from v17.setups.c6_microtrigger import compute_micro_signals
from v17.setups.c6_regime import compute_regime


def _ema(x: np.ndarray, period: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out
    alpha = 2.0 / (period + 1)
    out[0] = x[0]
    for i in range(1, n):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _in_entry_window(ts: pd.Timestamp) -> bool:
    start = ts.replace(
        hour=ENTRY_WINDOW_START_UTC_HM[0],
        minute=ENTRY_WINDOW_START_UTC_HM[1],
        second=0,
        microsecond=0,
    )
    end = ts.replace(
        hour=ENTRY_WINDOW_END_UTC_HM[0],
        minute=ENTRY_WINDOW_END_UTC_HM[1],
        second=0,
        microsecond=0,
    )
    if not (start <= ts <= end):
        return False
    bl_start = ts.replace(
        hour=NY_OPEN_BLACKOUT_UTC_HM[0][0],
        minute=NY_OPEN_BLACKOUT_UTC_HM[0][1],
        second=NY_OPEN_BLACKOUT_UTC_HM[0][2],
        microsecond=0,
    )
    bl_end = ts.replace(
        hour=NY_OPEN_BLACKOUT_UTC_HM[1][0],
        minute=NY_OPEN_BLACKOUT_UTC_HM[1][1],
        second=NY_OPEN_BLACKOUT_UTC_HM[1][2],
        microsecond=0,
    )
    if bl_start <= ts <= bl_end:
        return False
    return True


def _is_hard_flat(ts: pd.Timestamp) -> bool:
    return ts.hour == HARD_FLAT_HOUR_MIN_UTC[0] and ts.minute >= HARD_FLAT_HOUR_MIN_UTC[1]


def _initial_stop_long(bars_3: pd.DataFrame, entry: float, atr: float) -> float:
    swing = float(bars_3["bid_l"].min())
    floor = entry - ATR_FLOOR_MULT * atr
    return min(swing, floor)


def _initial_stop_short(bars_3: pd.DataFrame, entry: float, atr: float) -> float:
    swing = float(bars_3["ask_h"].max())
    floor = entry + ATR_FLOOR_MULT * atr
    return max(swing, floor)


def _trade_pnl_usd(pos: C6Position, pip_size: float, pip_value_fn) -> float:
    """
    Compute net P&L in USD for a fully closed position.

    Known approximation: pip_value_fn is called with pos.entry_price for all
    exit legs rather than per-exit price. Acceptable for intraday FX moves.
    """
    total = 0.0
    for e in pos.exit_log:
        lots = e["lots"]
        delta = (
            (e["price"] - pos.entry_price)
            if pos.side == "long"
            else (pos.entry_price - e["price"])
        )
        pip_value = pip_value_fn(pos.entry_price)
        total += (delta / pip_size) * pip_value * lots
    return total


def run_backtest(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    initial_equity: float,
    start_ts_ns: int,
    end_ts_ns: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run the Cycle 6 backtest over a shared M5 grid.

    Parameters
    ----------
    spx_m5 : SPX M5 DataFrame with ts_utc (int ns), bid/ask OHLC columns.
    fx_m5_by_sym : dict of symbol -> FX M5 DataFrame with same schema.
    calendar_idx : ForexFactory high-impact event index (may be empty).
    params : dict with keys "K", "slope_window", "C".
    initial_equity : starting equity in USD.
    start_ts_ns, end_ts_ns : inclusive timestamp bounds (int nanoseconds UTC).

    Returns
    -------
    (trade_log_df, equity_curve_df)
    """
    K = params["K"]
    slope_window = params["slope_window"]
    C = params["C"]

    # --- Pre-compute regime on the full SPX series ---
    regime_df = compute_regime(
        spx_m5,
        k_atr=K,
        slope_window=slope_window,
        session_anchor_hour=SESSION_ANCHOR_HOUR_UTC,
        atr_period=ATR_PERIOD,
    )
    regime = regime_df.set_index("ts_utc")

    # --- Pre-compute FX micro-signals and trailing EMA per pair ---
    sym_signals: dict[str, pd.DataFrame] = {}
    sym_ema: dict[str, pd.Series] = {}
    sym_df: dict[str, pd.DataFrame] = {}

    for cfg in C6_CATALOG:
        s = fx_m5_by_sym[cfg.symbol].copy().set_index("ts_utc")
        sym_df[cfg.symbol] = s
        sig = compute_micro_signals(
            s.reset_index(),
            confirm_body_mult=C,
            atr_period=ATR_PERIOD,
            session_anchor_hour=SESSION_ANCHOR_HOUR_UTC,
        ).set_index("ts_utc")
        sym_signals[cfg.symbol] = sig
        mid_c = ((s["bid_c"] + s["ask_c"]) * 0.5).to_numpy()
        sym_ema[cfg.symbol] = pd.Series(_ema(mid_c, TRAIL_EMA_PERIOD), index=s.index)

    # --- Shared time grid: inner-join of SPX + all FX timestamps ---
    shared_index = regime.index
    for cfg in C6_CATALOG:
        shared_index = shared_index.intersection(sym_df[cfg.symbol].index)
    shared_index = shared_index[
        (shared_index >= start_ts_ns) & (shared_index <= end_ts_ns)
    ]
    # Sort ascending for determinism; integer index is already sorted, but guard explicitly.
    shared_index = shared_index.sort_values()

    # --- Main loop ---
    open_positions: list[C6Position] = []
    closed: list[dict] = []
    equity_points: list[dict] = []
    equity = float(initial_equity)
    last_date: str = ""
    daily = DailyState(
        utc_date="",
        equity_sod=equity,
        realized_pnl=0.0,
        trade_count=0,
        consec_losses=0,
        locked=False,
        flatten_now=False,
    )

    for ts_ns in shared_index:
        ts = pd.Timestamp(ts_ns, tz="UTC")
        utc_date = ts.strftime("%Y-%m-%d")

        # Day roll-over: reset daily state.
        if utc_date != last_date:
            last_date = utc_date
            daily = DailyState(utc_date, equity, 0.0, 0, 0, False, False)

        # Calendar staleness guard (fail-closed: skip bar).
        if len(calendar_idx) > 0 and is_calendar_stale(ts_ns, calendar_idx, max_age_hours=48):
            continue

        hard_flat = _is_hard_flat(ts)

        # --- Advance open positions ---
        still_open: list[C6Position] = []
        for pos in open_positions:
            bar = sym_df[pos.symbol].loc[ts_ns].to_dict()
            bar["ts_utc"] = ts_ns
            ema20 = float(sym_ema[pos.symbol].loc[ts_ns])
            atr = float(sym_signals[pos.symbol].loc[ts_ns, "fx_atr"])
            pos = position_step(pos, bar, ema20=ema20, atr=atr, is_hard_flat=hard_flat)
            if not pos.leg_a_open and not pos.leg_b_open:
                cfg = next(c for c in C6_CATALOG if c.symbol == pos.symbol)
                pnl = _trade_pnl_usd(pos, cfg.pip_size, cfg.pip_value_per_lot)
                equity += pnl
                daily = update_after_trade(daily, pnl)
                daily = evaluate(daily)
                exits_a = [e for e in pos.exit_log if e["leg"] == "A"]
                exits_b = [e for e in pos.exit_log if e["leg"] == "B"]
                regime_at_entry = getattr(pos, "regime_at_entry", "?")
                closed.append({
                    "trade_id": pos.trade_id,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "regime_at_entry": regime_at_entry,
                    "entry_ts_ns": pos.entry_ts_ns,
                    "entry_price": pos.entry_price,
                    "initial_stop": pos.initial_stop,
                    "r_pips": int(round(pos.r_price / cfg.pip_size)),
                    "lots_a": pos.lots_a,
                    "lots_b": pos.lots_b,
                    "leg_a_exit_ts": exits_a[0]["ts_ns"] if exits_a else None,
                    "leg_a_exit_price": exits_a[0]["price"] if exits_a else None,
                    "leg_a_reason": exits_a[0]["reason"] if exits_a else None,
                    "leg_b_exit_ts": exits_b[0]["ts_ns"] if exits_b else None,
                    "leg_b_exit_price": exits_b[0]["price"] if exits_b else None,
                    "leg_b_reason": exits_b[0]["reason"] if exits_b else None,
                    "net_pnl_usd": pnl,
                    "r_multiple": pnl / (daily.equity_sod * RISK_PCT),
                    "equity_sod": daily.equity_sod,
                })
            else:
                still_open.append(pos)
        open_positions = still_open

        # Flatten all if daily circuit breaker fired.
        if daily.flatten_now and open_positions:
            remaining: list[C6Position] = []
            for pos in open_positions:
                bar = sym_df[pos.symbol].loc[ts_ns].to_dict()
                bar["ts_utc"] = ts_ns
                ema20 = float(sym_ema[pos.symbol].loc[ts_ns])
                atr = float(sym_signals[pos.symbol].loc[ts_ns, "fx_atr"])
                pos = position_step(pos, bar, ema20=ema20, atr=atr, is_hard_flat=True)
                # They are now all closed by hard-flat logic.
                cfg = next(c for c in C6_CATALOG if c.symbol == pos.symbol)
                pnl = _trade_pnl_usd(pos, cfg.pip_size, cfg.pip_value_per_lot)
                equity += pnl
                daily = update_after_trade(daily, pnl)
                exits_a = [e for e in pos.exit_log if e["leg"] == "A"]
                exits_b = [e for e in pos.exit_log if e["leg"] == "B"]
                regime_at_entry = getattr(pos, "regime_at_entry", "?")
                closed.append({
                    "trade_id": pos.trade_id,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "regime_at_entry": regime_at_entry,
                    "entry_ts_ns": pos.entry_ts_ns,
                    "entry_price": pos.entry_price,
                    "initial_stop": pos.initial_stop,
                    "r_pips": int(round(pos.r_price / cfg.pip_size)),
                    "lots_a": pos.lots_a,
                    "lots_b": pos.lots_b,
                    "leg_a_exit_ts": exits_a[0]["ts_ns"] if exits_a else None,
                    "leg_a_exit_price": exits_a[0]["price"] if exits_a else None,
                    "leg_a_reason": exits_a[0]["reason"] if exits_a else None,
                    "leg_b_exit_ts": exits_b[0]["ts_ns"] if exits_b else None,
                    "leg_b_exit_price": exits_b[0]["price"] if exits_b else None,
                    "leg_b_reason": exits_b[0]["reason"] if exits_b else None,
                    "net_pnl_usd": pnl,
                    "r_multiple": pnl / (daily.equity_sod * RISK_PCT) if daily.equity_sod > 0 else 0.0,
                    "equity_sod": daily.equity_sod,
                })
            open_positions = remaining  # empty
            daily = evaluate(daily)  # lock day: flatten_now→locked, invariant made local

        # --- Entry logic ---
        if not allow_entry(daily) or hard_flat or not _in_entry_window(ts):
            equity_points.append({"ts_utc": ts_ns, "equity": equity})
            continue

        reg_state = regime.loc[ts_ns, "regime_state"]
        if reg_state not in ("LONG_BIAS", "SHORT_BIAS"):
            equity_points.append({"ts_utc": ts_ns, "equity": equity})
            continue

        if len(calendar_idx) > 0 and is_blackout(ts_ns, calendar_idx, NEWS_BLACKOUT_MIN):
            equity_points.append({"ts_utc": ts_ns, "equity": equity})
            continue

        for cfg in C6_CATALOG:
            # Only one open position per pair.
            if any(p.symbol == cfg.symbol for p in open_positions):
                continue

            sig_row = sym_signals[cfg.symbol].loc[ts_ns]
            trigger_long = reg_state == "LONG_BIAS" and bool(sig_row["confirm_long"])
            trigger_short = reg_state == "SHORT_BIAS" and bool(sig_row["confirm_short"])
            if not (trigger_long or trigger_short):
                continue
            side = "long" if trigger_long else "short"

            # Entry fills at bar t+1 open — no look-ahead beyond one bar.
            idx_arr = sym_df[cfg.symbol].index
            idx_pos = idx_arr.get_indexer([ts_ns])[0]
            if idx_pos < 0 or idx_pos + 1 >= len(idx_arr):
                continue
            next_bar = sym_df[cfg.symbol].iloc[idx_pos + 1]
            entry = float(next_bar["ask_o"] if side == "long" else next_bar["bid_o"])

            bars_3 = sym_df[cfg.symbol].iloc[max(0, idx_pos - 2):idx_pos + 1]
            atr = float(sig_row["fx_atr"])
            if np.isnan(atr) or atr <= 0:
                continue

            if side == "long":
                stop = _initial_stop_long(bars_3, entry, atr)
            else:
                stop = _initial_stop_short(bars_3, entry, atr)

            lots_a, lots_b, r_pips = size_position(
                cfg.symbol, daily.equity_sod, RISK_PCT, entry, stop
            )
            if lots_a == 0:
                continue

            # Portfolio cap: skip if combined open risk > 0.75% of equity_sod.
            cur_open_risk = 0.0
            for p in open_positions:
                cfg_p = next(c for c in C6_CATALOG if c.symbol == p.symbol)
                lots_open = (p.lots_a if p.leg_a_open else 0.0) + (
                    p.lots_b if p.leg_b_open else 0.0
                )
                price_now = float(sym_df[p.symbol].loc[ts_ns, "bid_c"])
                stop_now = p.leg_b_stop
                cur_open_risk += (
                    abs(price_now - stop_now)
                    / cfg_p.pip_size
                    * cfg_p.pip_value_per_lot(price_now)
                    * lots_open
                )
            new_risk = (lots_a + lots_b) * r_pips * cfg.pip_value_per_lot(entry)
            if cur_open_risk + new_risk > PORTFOLIO_RISK_PCT * daily.equity_sod:
                continue

            pos = C6Position(
                trade_id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_OID, f"{cfg.symbol}-{ts_ns}-{side}"
                    )
                ),
                symbol=cfg.symbol,
                side=side,
                entry_ts_ns=int(next_bar.name),  # index is ts_utc (int ns)
                entry_price=entry,
                initial_stop=stop,
                r_price=abs(entry - stop),
                lots_a=lots_a,
                lots_b=lots_b,
                leg_a_open=True,
                leg_b_open=True,
                leg_b_stop=stop,
                breakeven_hit=False,
                exit_log=[],
            )
            pos.regime_at_entry = reg_state  # type: ignore[attr-defined]
            open_positions.append(pos)

        equity_points.append({"ts_utc": ts_ns, "equity": equity})

    trade_log = pd.DataFrame(closed)
    equity_curve = pd.DataFrame(equity_points)
    return trade_log, equity_curve
