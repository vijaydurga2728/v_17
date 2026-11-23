"""CHoCH + FVG FADED probe on H1 bars — paper flagship replication.

Reference: Mahadzva (2026), "Smart Money or Costly Folklore?", Study 6.
Flagship result: EURUSD H1, p=0.0192, WFE 1.58, holdout +19.3%, PF 1.50.

Mechanic (paper, verbatim):
  1. Track regime via swing structure. Bullish regime = last decisive swing
     break was upward (close above most recent swing high). Bearish mirror.
  2. CHoCH = regime flip. The flipping bar is the "break bar".
  3. Rally extreme = running max/min during the flipping impulse. This is
     the "origin" used for stop anchoring.
  4. FVG detection: at bar k using bars k-2, k-1, k.
     Bullish FVG (gap up): low[k] > high[k-2]. Zone = [high[k-2], low[k]].
     Bearish FVG (gap down): high[k] < low[k-2]. Zone = [high[k], low[k-2]].
     FVG armed if direction of gap matches the rally that caused CHoCH.
  5. Setup invalidates if price closes back beyond the rally origin before
     retracing into the FVG.
  6. Entry: first bar after CHoCH that trades back into the armed FVG.
  7. FADE: SHORT on bullish CHoCH (fade the "reversal"), LONG on bearish.
  8. SL: at rally origin + 0.5 ATR buffer (paper's min_stop_atr=0.5 floor).
  9. TP: 2R.
  10. One trade per CHoCH event. No active positions overlap.

Run on EURUSD + GBPUSD dev 2015-2024 (H1 from M1 resample).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from v17.data.parquet_store import read_bars


ATR_PERIOD = 14
SWING_LEFT = 3
SWING_RIGHT = 3
MIN_STOP_ATR = 0.5
RR_TARGET = 2.0


def _resample_h1(m1: pd.DataFrame) -> pd.DataFrame:
    """Resample M1 bars to H1 using bid-side OHLC + volume sum."""
    df = m1.copy()
    df["_ts"] = pd.to_datetime(df["ts_utc"], utc=True)
    df = df.set_index("_ts").sort_index()
    agg = df.resample("1h", label="left", closed="left").agg(
        ts_utc=("ts_utc", "first"),
        bid_o=("bid_o", "first"),
        bid_h=("bid_h", "max"),
        bid_l=("bid_l", "min"),
        bid_c=("bid_c", "last"),
        ask_o=("ask_o", "first"),
        ask_h=("ask_h", "max"),
        ask_l=("ask_l", "min"),
        ask_c=("ask_c", "last"),
        bid_volume=("bid_volume", "sum"),
        ask_volume=("ask_volume", "sum"),
    ).dropna().reset_index(drop=True)
    return agg


def _atr14(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return pd.Series(tr).rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean().to_numpy()


def _swings(h: np.ndarray, l: np.ndarray, left: int, right: int) -> tuple:
    """Return (swing_high_idx, swing_high_val, swing_low_idx, swing_low_val) lists.
    Causal — swing at i is confirmed only after bar i+right."""
    n = len(h)
    sh_idx: list[int] = []
    sh_val: list[float] = []
    sl_idx: list[int] = []
    sl_val: list[float] = []
    for i in range(left, n - right):
        if h[i] == max(h[i - left:i + right + 1]):
            sh_idx.append(i)
            sh_val.append(float(h[i]))
        if l[i] == min(l[i - left:i + right + 1]):
            sl_idx.append(i)
            sl_val.append(float(l[i]))
    return sh_idx, sh_val, sl_idx, sl_val


def run_one_symbol(symbol: str, bars_m1: pd.DataFrame) -> pd.DataFrame:
    h1 = _resample_h1(bars_m1)
    n = len(h1)
    bh = h1["bid_h"].to_numpy(float)
    bl = h1["bid_l"].to_numpy(float)
    bc = h1["bid_c"].to_numpy(float)
    ah = h1["ask_h"].to_numpy(float)
    al = h1["ask_l"].to_numpy(float)
    ac = h1["ask_c"].to_numpy(float)
    ts = h1["ts_utc"].to_numpy(np.int64)
    atr = _atr14(bh, bl, bc)

    sh_idx, sh_val, sl_idx, sl_val = _swings(bh, bl, SWING_LEFT, SWING_RIGHT)

    # Convert swing lists to arrays for searchsorted
    sh_idx_arr = np.array(sh_idx, dtype=np.int64)
    sh_val_arr = np.array(sh_val, dtype=float)
    sl_idx_arr = np.array(sl_idx, dtype=np.int64)
    sl_val_arr = np.array(sl_val, dtype=float)

    def last_confirmed_swing_high(bar_i):
        """Last swing high confirmed by bar_i: swing idx + right < bar_i."""
        if len(sh_idx_arr) == 0:
            return None, None
        confirmed_cutoff = bar_i - SWING_RIGHT
        pos = np.searchsorted(sh_idx_arr, confirmed_cutoff, side="right") - 1
        while pos >= 0 and sh_idx_arr[pos] + SWING_RIGHT >= bar_i:
            pos -= 1
        if pos < 0:
            return None, None
        return int(sh_idx_arr[pos]), float(sh_val_arr[pos])

    def last_confirmed_swing_low(bar_i):
        if len(sl_idx_arr) == 0:
            return None, None
        confirmed_cutoff = bar_i - SWING_RIGHT
        pos = np.searchsorted(sl_idx_arr, confirmed_cutoff, side="right") - 1
        while pos >= 0 and sl_idx_arr[pos] + SWING_RIGHT >= bar_i:
            pos -= 1
        if pos < 0:
            return None, None
        return int(sl_idx_arr[pos]), float(sl_val_arr[pos])

    # Regime tracking
    regime = "NONE"  # "BULLISH" or "BEARISH"
    regime_start_idx = 0
    # Running extreme during current regime's forming impulse
    rally_extreme = None  # low (bullish rally from this low) or high (bearish rally from this high)
    rally_extreme_idx = None

    trades = []
    active_fvg = None  # dict with keys: direction, top, bottom, confirmed_idx, origin_price
    cooldown_until = 0

    for i in range(max(SWING_LEFT + SWING_RIGHT + 1, ATR_PERIOD + 1), n):
        if i < cooldown_until:
            continue

        # Check for FVG formed at bar i-1 using bars i-3, i-2, i-1 (causal)
        # Here we track FVG as it forms during the rally; arm when CHoCH confirms.
        # For simplicity: we re-check FVGs on bar i (causally-safe since we use i-2, i-1 only)

        # Try to detect CHoCH on bar i
        # Bullish CHoCH: previous regime BEARISH, and bar i's close > last confirmed swing high
        # Bearish CHoCH: previous regime BULLISH, and bar i's close < last confirmed swing low
        choch_fired = None
        rally_origin = None

        sh_last_idx, sh_last_val = last_confirmed_swing_high(i)
        sl_last_idx, sl_last_val = last_confirmed_swing_low(i)

        if regime != "BULLISH" and sh_last_val is not None and bc[i] > sh_last_val:
            # Bullish CHoCH confirmed at bar i. Rally origin = lowest low since regime started.
            lookback_start = regime_start_idx if regime == "BEARISH" else max(0, i - 60)
            rally_origin = float(bl[lookback_start:i + 1].min())
            # Find most recent bullish FVG in [lookback_start, i]
            best_fvg = None
            for k in range(max(lookback_start, 2), i + 1):
                if bl[k] > bh[k - 2]:
                    best_fvg = {
                        "direction": "BULLISH",
                        "bottom": float(bh[k - 2]),
                        "top": float(bl[k]),
                        "confirmed_idx": k,
                    }
            if best_fvg is not None:
                active_fvg = {
                    **best_fvg,
                    "choch_bar": i,
                    "origin_price": rally_origin,
                }
                choch_fired = "BULLISH"
            regime = "BULLISH"
            regime_start_idx = i

        elif regime != "BEARISH" and sl_last_val is not None and bc[i] < sl_last_val:
            lookback_start = regime_start_idx if regime == "BULLISH" else max(0, i - 60)
            rally_origin = float(bh[lookback_start:i + 1].max())
            best_fvg = None
            for k in range(max(lookback_start, 2), i + 1):
                if bh[k] < bl[k - 2]:
                    best_fvg = {
                        "direction": "BEARISH",
                        "bottom": float(bh[k]),
                        "top": float(bl[k - 2]),
                        "confirmed_idx": k,
                    }
            if best_fvg is not None:
                active_fvg = {
                    **best_fvg,
                    "choch_bar": i,
                    "origin_price": rally_origin,
                }
                choch_fired = "BEARISH"
            regime = "BEARISH"
            regime_start_idx = i

        # If an active FVG exists, check for invalidation or entry
        if active_fvg is None:
            continue

        # Invalidation: close back beyond rally origin
        if active_fvg["direction"] == "BULLISH":
            if bc[i] < active_fvg["origin_price"]:
                active_fvg = None
                continue
        else:
            if bc[i] > active_fvg["origin_price"]:
                active_fvg = None
                continue

        # Entry: bar i trades back into FVG (and is not the FVG-confirming bar itself)
        if i <= active_fvg["confirmed_idx"]:
            continue
        in_fvg = (bl[i] <= active_fvg["top"]) and (bh[i] >= active_fvg["bottom"])
        if not in_fvg:
            continue

        # Trade entry — FADE the CHoCH direction
        choch_dir = active_fvg["direction"]
        side = "SHORT" if choch_dir == "BULLISH" else "LONG"
        atr_entry = float(atr[i])
        if not np.isfinite(atr_entry) or atr_entry <= 0:
            active_fvg = None
            continue

        # Entry price: FADE execution. SHORT sells at bid_c, LONG buys at ask_c.
        if side == "SHORT":
            entry_px = float(bc[i])
            # SL = origin + 0.5 ATR (above the bullish rally extreme — paper's floor)
            sl_px = active_fvg["top"] + MIN_STOP_ATR * atr_entry
            risk = sl_px - entry_px
            if risk <= 0:
                active_fvg = None
                continue
            tp_px = entry_px - RR_TARGET * risk
        else:
            entry_px = float(ac[i])
            sl_px = active_fvg["bottom"] - MIN_STOP_ATR * atr_entry
            risk = entry_px - sl_px
            if risk <= 0:
                active_fvg = None
                continue
            tp_px = entry_px + RR_TARGET * risk

        # Walk forward for max 48 H1 bars (2 trading days) to resolve exit
        exit_idx = None
        exit_px = None
        exit_reason = None
        max_horizon = min(i + 48, n)
        for j in range(i + 1, max_horizon):
            if side == "LONG":
                hit_sl = bl[j] <= sl_px
                hit_tp = ah[j] >= tp_px
            else:
                hit_sl = ah[j] >= sl_px
                hit_tp = bl[j] <= tp_px
            if hit_sl and hit_tp:
                exit_idx, exit_px, exit_reason = j, sl_px, "SL"
                break
            if hit_sl:
                exit_idx, exit_px, exit_reason = j, sl_px, "SL"
                break
            if hit_tp:
                exit_idx, exit_px, exit_reason = j, tp_px, "TP"
                break
        if exit_idx is None:
            exit_idx = max_horizon - 1
            exit_px = float(bc[exit_idx] if side == "LONG" else ac[exit_idx])
            exit_reason = "TIME"

        pnl_r = ((exit_px - entry_px) / risk) if side == "LONG" else ((entry_px - exit_px) / risk)

        trades.append({
            "symbol": symbol,
            "entry_ts_ns": int(ts[i]),
            "choch_direction": choch_dir,
            "side": side,
            "entry_px": entry_px, "sl_px": sl_px, "tp_px": tp_px,
            "exit_ts_ns": int(ts[exit_idx]), "exit_px": exit_px,
            "exit_reason": exit_reason, "risk": risk, "pnl_r": pnl_r,
            "atr_entry": atr_entry, "fvg_top": active_fvg["top"], "fvg_bottom": active_fvg["bottom"],
            "origin_price": active_fvg["origin_price"],
        })

        active_fvg = None
        cooldown_until = exit_idx + 1

    return pd.DataFrame(trades)


def _summarize(sym, df, years):
    n = len(df)
    if n == 0:
        print(f"\n{sym}: 0 trades. SKIP.")
        return
    wins = df[df["pnl_r"] > 0]
    losses = df[df["pnl_r"] < 0]
    pf = wins["pnl_r"].sum() / abs(losses["pnl_r"].sum()) if abs(losses["pnl_r"].sum()) > 0 else float("inf")
    equity = df["pnl_r"].cumsum().to_numpy()
    peak = np.maximum.accumulate(equity)
    max_dd = float((peak - equity).max())
    print(f"\n{sym} H1 CHoCH+FVG FADED:")
    print(f"  trades: {n}  (trades/year: {n/years:.1f}, trades/month: {n/years/12:.2f})")
    print(f"  WR: {(df.pnl_r > 0).mean()*100:.1f}%")
    print(f"  PF: {pf:.2f}")
    print(f"  mean R: {df.pnl_r.mean():+.3f}")
    print(f"  sum R: {df.pnl_r.sum():+.2f}")
    print(f"  max DD (R): {max_dd:.2f}")
    print(f"  sides: {df['side'].value_counts().to_dict()}")
    print(f"  exits: {df['exit_reason'].value_counts().to_dict()}")
    ann_r = n / years * df.pnl_r.mean()
    print(f"  Annualized R: {ann_r:+.2f}  → at 0.5% risk on $10k: ${ann_r*50:+.0f}/year")


def main():
    results_root = Path("research/results")
    results_root.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    all_trades = []
    for sym in ["EURUSD", "GBPUSD"]:
        print(f"[{time.strftime('%H:%M:%S')}] load {sym} M1 dev bars...", flush=True)
        m1 = read_bars(root=Path("data"), symbol=sym, partition="dev", dev_only=True)
        print(f"  {len(m1):,} M1 bars", flush=True)
        ts = pd.to_datetime(m1["ts_utc"], utc=True)
        years = (ts.max() - ts.min()).days / 365.25

        print(f"[{time.strftime('%H:%M:%S')}] scan {sym} H1 CHoCH+FVG faded...", flush=True)
        t_s = time.time()
        trades = run_one_symbol(sym, m1)
        print(f"  {len(trades)} trades in {time.time()-t_s:.1f}s", flush=True)
        trades.to_parquet(results_root / f"choch_fvg_faded_{sym}.parquet", index=False)
        _summarize(sym, trades, years)
        all_trades.append(trades)

    combined = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    if len(combined) > 0:
        print("\n" + "=" * 72)
        total_years = 10.0
        _summarize("COMBINED", combined, total_years * 2)
        pf_combined = combined[combined.pnl_r > 0].pnl_r.sum() / max(1e-9, abs(combined[combined.pnl_r < 0].pnl_r.sum()))
        if pf_combined >= 1.3 and len(combined) >= 60:
            print(f"\nDECISION: GREEN — PF {pf_combined:.2f} ≥ 1.3 AND {len(combined)} trades ≥ 60. Matches paper's flagship.")
        else:
            print(f"\nDECISION: RED — PF {pf_combined:.2f} / trades {len(combined)}. Does not replicate paper's flagship on this data.")
    print(f"\nWall clock: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
