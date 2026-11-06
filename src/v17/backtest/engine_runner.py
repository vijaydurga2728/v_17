"""Per-engine OOS runner — full context assembly (Task 5.3).

Wires D1 bias, ATR_14 rolling, SpreadGuard, liquidity pools,
sweep-confirmation, displacement + FVG detection, and compute_sl_tp
so trades fire with real SL/TP/R:R.

Public API preserved:
  - TradeLog dataclass
  - run_engine_oos(config, bars, calendar, fold) -> TradeLog

Optimised (Task 8.0):
  O1 — FVGs precomputed once per symbol (not per bar).
  O2 — Session/prev-hour pools computed once per day at window_start_ns.
  O3 — Inner loop uses numpy arrays; iterrows eliminated.
  O4 — Sweep check uses pre-extracted scalar min/max pool prices.
  O5 — ATR_14 already fold-scoped; unchanged.
  O6 — bar dict built only when all prior gates pass.
  SG  — SpreadGuard precomputes per-MoD trailing-30d medians upfront.
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
    SPREAD_GUARD_LOOKBACK_DAYS,
    SPREAD_GUARD_MULT,
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
_NS_PER_HOUR: int = 3_600_000_000_000
_NS_PER_DAY: int = 86_400_000_000_000
_30D_NS: int = SPREAD_GUARD_LOOKBACK_DAYS * _NS_PER_DAY


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
        # SB-05: NEAREST opposing pool above entry (not farthest).
        candidates = [
            p["price"]
            for p in pools
            if p["kind"].endswith("_high") and p["price"] > entry
        ]
        if candidates:
            return min(candidates)
        fallback_dist = (
            STRUCTURAL_FALLBACK_USATECH_PTS if is_index
            else STRUCTURAL_FALLBACK_FX_PIPS * pip
        )
        return entry + fallback_dist
    else:  # SHORT
        # SB-05: NEAREST opposing pool below entry (not farthest).
        candidates = [
            p["price"]
            for p in pools
            if p["kind"].endswith("_low") and p["price"] < entry
        ]
        if candidates:
            return max(candidates)
        fallback_dist = (
            STRUCTURAL_FALLBACK_USATECH_PTS if is_index
            else STRUCTURAL_FALLBACK_FX_PIPS * pip
        )
        return entry - fallback_dist


# ---------------------------------------------------------------------------
# O1: precomputed FVG lookup helpers
# ---------------------------------------------------------------------------

class _FVGCache:
    """Precomputed FVG arrays for O(log n) per-bar lookup.

    At window start (as_of_ns = bar_ts + _NS_PER_MIN) the matching bar is
    the one at ts_ns == bar_ts with as_of_ns = bar_ts + 60s. The original
    detect_fvgs_at returns all FVGs whose causal bar's ts_ns < as_of_ns.
    We precompute ALL FVGs (using max ts + 1 as as_of_ns) then filter to
    ts_ns < (bar_ts + _NS_PER_MIN) == ts_ns <= bar_ts at bar granularity.
    """

    def __init__(self, all_sym: pd.DataFrame):
        # Precompute every FVG for the symbol's full history.
        max_ts = int(all_sym["ts_utc"].max())
        all_fvgs: list[dict] = detect_fvgs_at(all_sym, as_of_ns=max_ts + 1)

        if not all_fvgs:
            self._ts_arr: np.ndarray = np.array([], dtype=np.int64)
            self._kinds: list[str] = []
            self._tops: np.ndarray = np.array([], dtype=np.float64)
            self._bottoms: np.ndarray = np.array([], dtype=np.float64)
            self._ces: np.ndarray = np.array([], dtype=np.float64)
            return

        self._ts_arr = np.array([f["ts_ns"] for f in all_fvgs], dtype=np.int64)
        self._kinds = [f["kind"] for f in all_fvgs]
        self._tops = np.array([f["top"] for f in all_fvgs], dtype=np.float64)
        self._bottoms = np.array([f["bottom"] for f in all_fvgs], dtype=np.float64)
        self._ces = np.array([f["ce"] for f in all_fvgs], dtype=np.float64)

    def latest_at_ts(self, bar_ts: int, expected_kind: str) -> Optional[dict]:
        """Return the last FVG with ts_ns == bar_ts and matching kind, or None.

        Equivalent to: [f for f in detect_fvgs_at(all_sym, bar_ts + 1_min)
                         if f['kind'] == expected_kind and f['ts_ns'] == bar_ts][-1]
        """
        if len(self._ts_arr) == 0:
            return None
        # All FVGs with ts_ns == bar_ts (the displacement bar).
        mask = self._ts_arr == bar_ts
        if not mask.any():
            return None
        idxs = np.where(mask)[0]
        # Filter by kind; take last match.
        for idx in reversed(idxs):
            if self._kinds[idx] == expected_kind:
                return {
                    "kind": self._kinds[idx],
                    "ts_ns": int(self._ts_arr[idx]),
                    "top": float(self._tops[idx]),
                    "bottom": float(self._bottoms[idx]),
                    "ce": float(self._ces[idx]),
                }
        return None

    def visible_at(self, as_of_ns: int) -> list[dict]:
        """Return all FVGs visible as of as_of_ns (ts_ns < as_of_ns).

        Used to pass fvgs list to FSM context — identical to detect_fvgs_at result.
        """
        if len(self._ts_arr) == 0:
            return []
        cut = np.searchsorted(self._ts_arr, as_of_ns, side="left")
        return [
            {
                "kind": self._kinds[i],
                "ts_ns": int(self._ts_arr[i]),
                "top": float(self._tops[i]),
                "bottom": float(self._bottoms[i]),
                "ce": float(self._ces[i]),
            }
            for i in range(cut)
        ]


# ---------------------------------------------------------------------------
# O(1) SpreadGuard via precomputed MoD medians
# ---------------------------------------------------------------------------

class _FastSpreadGuard:
    """Precompute trailing-30d medians keyed by (minute_of_day, day_offset).

    Strategy: build one median per (MoD) over the 30-day rolling window for
    each timestamp in the OOS slice. This precompute is O(n_bars) once and
    makes per-bar rejection O(1).

    Implementation: for each MoD bucket in [0, 1440), compute a list of
    (ts_utc_ns, spread) sorted by ts_utc_ns. At query time, binary-search
    to find the 30d trailing window and return median.

    To avoid Python-level per-bar binary search, we precompute the median
    for every OOS bar timestamp up front.
    """

    def __init__(self, all_sym: pd.DataFrame, symbol: str, oos_ts_array: np.ndarray):
        df = all_sym[all_sym["symbol"] == symbol][["ts_utc", "spread_mid"]].copy()
        if df.empty:
            self._reject_arr: np.ndarray = np.zeros(len(oos_ts_array), dtype=bool)
            return

        ts_pd = pd.to_datetime(df["ts_utc"], utc=True)
        df["_mod"] = ts_pd.dt.hour * 60 + ts_pd.dt.minute
        df = df.sort_values("ts_utc").reset_index(drop=True)

        df_ts = df["ts_utc"].to_numpy(dtype=np.int64)
        df_mod = df["_mod"].to_numpy(dtype=np.int64)
        df_sp = df["spread_mid"].to_numpy(dtype=np.float64)

        # Group indices by MoD for fast lookup.
        from collections import defaultdict
        mod_indices: dict[int, list[int]] = defaultdict(list)
        for i, m in enumerate(df_mod):
            mod_indices[int(m)].append(i)

        # For each OOS timestamp, compute should_reject.
        n = len(oos_ts_array)
        reject = np.zeros(n, dtype=bool)

        # We also need OOS spreads. Build lookup from OOS ts → spread.
        # oos_ts_array is from oos_bars, so spreads are in oos_bars directly.
        # We'll compute it during the main loop instead; just store median table.
        # Build: for each OOS ts, find mod → find trailing 30d window median.
        oos_pd = pd.to_datetime(oos_ts_array, utc=True)
        oos_mods = oos_pd.hour * 60 + oos_pd.minute  # numpy-friendly

        # Precompute median per OOS bar.
        self._median_arr = np.full(n, np.nan, dtype=np.float64)
        for j in range(n):
            bar_ts = int(oos_ts_array[j])
            mod = int(oos_mods[j])
            idxs = mod_indices.get(mod)
            if not idxs:
                continue
            window_start = bar_ts - _30D_NS
            # Binary search over df_ts at these indices.
            # idxs are sorted because we iterated df in ts order.
            # Find first idx with df_ts[idx] >= window_start.
            lo, hi = 0, len(idxs)
            while lo < hi:
                mid_i = (lo + hi) // 2
                if df_ts[idxs[mid_i]] < window_start:
                    lo = mid_i + 1
                else:
                    hi = mid_i
            # Find last idx with df_ts[idx] < bar_ts.
            lo2, hi2 = lo, len(idxs)
            while lo2 < hi2:
                mid_i = (lo2 + hi2) // 2
                if df_ts[idxs[mid_i]] < bar_ts:
                    lo2 = mid_i + 1
                else:
                    hi2 = mid_i
            window_idxs = idxs[lo:lo2]
            if window_idxs:
                self._median_arr[j] = float(np.median(df_sp[window_idxs]))

        # Store OOS index for fast lookup.
        self._oos_ts_to_j: dict[int, int] = {
            int(oos_ts_array[j]): j for j in range(n)
        }

    def should_reject_fast(self, bar_ts: int, current_spread: float) -> bool:
        j = self._oos_ts_to_j.get(bar_ts)
        if j is None:
            return False
        median = self._median_arr[j]
        if np.isnan(median):
            return False
        return current_spread > SPREAD_GUARD_MULT * median


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

        # O1: Precompute ALL FVGs for this symbol once.
        fvg_cache = _FVGCache(all_sym)

        # O3: Extract OOS bar columns as numpy arrays (indexed 0..N-1).
        arr_ts = oos_bars["ts_utc"].to_numpy(dtype=np.int64)
        arr_bh = oos_bars["bid_h"].to_numpy(dtype=np.float64)
        arr_bl = oos_bars["bid_l"].to_numpy(dtype=np.float64)
        arr_bo = oos_bars["bid_o"].to_numpy(dtype=np.float64)
        arr_bc = oos_bars["bid_c"].to_numpy(dtype=np.float64)
        arr_sp = oos_bars["spread_mid"].to_numpy(dtype=np.float64)
        arr_atr = atr_series.reindex(oos_bars.index).to_numpy(dtype=np.float64)

        # SpreadGuard: precomputed fast version using OOS timestamps.
        fast_sg = _FastSpreadGuard(all_sym, symbol, arr_ts)

        # Build ts->row-index map for window slicing.
        # (Used to find start/end indices in oos_bars for each day window.)
        # arr_ts is already sorted ascending (OOS slice, copy, reset_index).

        # all_sym numpy arrays for per-day pool computation (O2).
        all_ts_np = all_sym["ts_utc"].to_numpy(dtype=np.int64)
        all_bh_np = all_sym["bid_h"].to_numpy(dtype=np.float64)
        all_bl_np = all_sym["bid_l"].to_numpy(dtype=np.float64)

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

            # O2: Compute session/prev-hour pools ONCE per day at window_start_ns.
            # session scope: [ny_midnight, window_start_ns) in all_sym.
            ny_midnight_ns = int(
                pd.Timestamp(ny_date, tz="America/New_York").tz_convert("UTC").value
            )

            # Find indices in all_sym for session scope.
            pre_win_mask = (all_ts_np >= ny_midnight_ns) & (all_ts_np < window_start_ns)
            if pre_win_mask.any():
                pre_bh = all_bh_np[pre_win_mask]
                pre_bl = all_bl_np[pre_win_mask]
                pre_ts = all_ts_np[pre_win_mask]
                session_high_price = float(pre_bh.max())
                session_low_price = float(pre_bl.min())
                sh_ts = int(pre_ts[pre_bh.argmax()])
                sl_ts = int(pre_ts[pre_bl.argmin()])
            else:
                session_high_price = None
                session_low_price = None
                sh_ts = 0
                sl_ts = 0

            prev_hr_mask = (
                (all_ts_np >= window_start_ns - _NS_PER_HOUR)
                & (all_ts_np < window_start_ns)
            )
            if prev_hr_mask.any():
                ph_bh = all_bh_np[prev_hr_mask]
                ph_bl = all_bl_np[prev_hr_mask]
                ph_ts = all_ts_np[prev_hr_mask]
                prev_hour_high_price = float(ph_bh.max())
                prev_hour_low_price = float(ph_bl.min())
                phh_ts = int(ph_ts[ph_bh.argmax()])
                phl_ts = int(ph_ts[ph_bl.argmin()])
            else:
                prev_hour_high_price = None
                prev_hour_low_price = None
                phh_ts = 0
                phl_ts = 0

            # Build locked pools list once per day.
            pools: list[dict] = []
            if session_high_price is not None:
                pools.append({"kind": "session_high", "price": session_high_price, "ts_utc": sh_ts})
                pools.append({"kind": "session_low", "price": session_low_price, "ts_utc": sl_ts})
            if prev_hour_high_price is not None:
                pools.append({"kind": "prev_hour_high", "price": prev_hour_high_price, "ts_utc": phh_ts})
                pools.append({"kind": "prev_hour_low", "price": prev_hour_low_price, "ts_utc": phl_ts})

            if not pools:
                continue

            # O4: Pre-extract scalar sweep thresholds from fixed pools.
            if d1_bias == "BULLISH":
                low_pool_prices = [p["price"] for p in pools if p["kind"].endswith("_low")]
                sweep_threshold = min(low_pool_prices) if low_pool_prices else None
            else:  # BEARISH
                high_pool_prices = [p["price"] for p in pools if p["kind"].endswith("_high")]
                sweep_threshold = max(high_pool_prices) if high_pool_prices else None

            if sweep_threshold is None:
                continue

            # Find OOS bar indices for this day's window.
            # arr_ts is sorted; use searchsorted.
            win_lo = int(np.searchsorted(arr_ts, window_start_ns, side="left"))
            win_hi = int(np.searchsorted(arr_ts, window_end_ns, side="left"))
            if win_lo >= win_hi:
                continue

            # Per-day sweep state
            sweep_confirmed = False
            sweep_extreme: Optional[float] = None
            swept_pool_kind: Optional[str] = None
            displacement_bar_fvg: Optional[dict] = None

            # O3: Iterate via numpy index.
            for i in range(win_lo, win_hi):
                bar_ts = int(arr_ts[i])

                # Hard exit: no entries at or beyond window_end
                if bar_ts >= window_end_ns:
                    break

                # ATR check
                atr_14 = arr_atr[i]
                if np.isnan(atr_14) or atr_14 <= 0:
                    continue

                # Blackout gate (calendar is typically empty in pilot; fast path)
                if is_in_blackout(bar_ts, calendar, currencies):
                    continue

                # Spread guard — fast precomputed O(1) lookup
                current_spread = arr_sp[i]
                if fast_sg.should_reject_fast(bar_ts, current_spread):
                    continue

                # O4: Sweep confirmation using pre-extracted scalar threshold.
                if not sweep_confirmed:
                    if d1_bias == "BULLISH":
                        # Any _low pool swept iff bid_l < its price.
                        # We use min(low_pool_prices) for a conservative check:
                        # if bid_l < min_low, it's definitely below at least one pool.
                        # But we need to track which pool was swept for swept_pool_kind.
                        bid_l_i = arr_bl[i]
                        for p in pools:
                            if p["kind"].endswith("_low") and bid_l_i < p["price"]:
                                sweep_confirmed = True
                                swept_pool_kind = p["kind"]
                                sweep_extreme = bid_l_i
                                break
                    else:  # BEARISH
                        bid_h_i = arr_bh[i]
                        for p in pools:
                            if p["kind"].endswith("_high") and bid_h_i > p["price"]:
                                sweep_confirmed = True
                                swept_pool_kind = p["kind"]
                                sweep_extreme = bid_h_i
                                break

                if not sweep_confirmed:
                    continue

                # Update sweep extreme with running min/max
                if d1_bias == "BULLISH" and sweep_extreme is not None:
                    v = arr_bl[i]
                    if v < sweep_extreme:
                        sweep_extreme = v
                elif d1_bias == "BEARISH" and sweep_extreme is not None:
                    v = arr_bh[i]
                    if v > sweep_extreme:
                        sweep_extreme = v

                # O1: FVG lookup — O(log n) via precomputed cache.
                expected_kind = "bullish" if d1_bias == "BULLISH" else "bearish"
                fvg_match = fvg_cache.latest_at_ts(bar_ts, expected_kind)

                # O6: Build bar dict only when needed (after all prior gates pass).
                if fvg_match is not None:
                    bar = {
                        "ts_utc": bar_ts,
                        "symbol": symbol,
                        "bid_o": float(arr_bo[i]),
                        "bid_h": float(arr_bh[i]),
                        "bid_l": float(arr_bl[i]),
                        "bid_c": float(arr_bc[i]),
                        "spread_mid": float(current_spread),
                    }
                    if is_displacement(bar, atr_14):
                        displacement_bar_fvg = fvg_match

                if displacement_bar_fvg is None:
                    continue

                # O6: bar dict already built above if fvg_match was set.
                # If displacement_bar_fvg was set in a prior iteration,
                # we need bar dict here for fsm.step.
                if fvg_match is None:
                    bar = {
                        "ts_utc": bar_ts,
                        "symbol": symbol,
                        "bid_o": float(arr_bo[i]),
                        "bid_h": float(arr_bh[i]),
                        "bid_l": float(arr_bl[i]),
                        "bid_c": float(arr_bc[i]),
                        "spread_mid": float(current_spread),
                    }

                # FVGs visible as of bar_ts + 1min (for FSM context)
                as_of_ns = bar_ts + _NS_PER_MIN
                fvgs_ctx = fvg_cache.visible_at(as_of_ns)

                # Build context for FSM
                context = {
                    "d1_bias": d1_bias,
                    "atr_14": atr_14,
                    "spread": current_spread,
                    "spread_median": 0.0,  # FSM uses spread guard separately; pass 0 to skip FSM dupe check
                    "calendar_blackout": False,  # already gated above
                    "window_open": True,
                    "liquidity_pools": pools,
                    "fvgs": fvgs_ctx,
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
                bid_l_i = arr_bl[i]
                bid_h_i = arr_bh[i]
                if config.entry_model == "CE":
                    ce = sig.entry_price
                    if not (bid_l_i <= ce <= bid_h_i):
                        continue
                else:  # AGGRESSIVE: fill at top (LONG) or bottom (SHORT)
                    target_edge = sig.entry_price
                    if not (bid_l_i <= target_edge <= bid_h_i):
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
