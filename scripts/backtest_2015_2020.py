"""Backtest 2015-2020: Institutional Silver Bullet across EURUSD, GBPUSD, US500, XAUUSD.

Zero Lookahead Guaranteed:
- M5 Pivots confirmed only after 2 closed right bars.
- HTF Draw on Liquidity (DOL) from closed D1 PDH/PDL and Asian reference range.
- Dealing Range Equilibrium Guard: Longs strictly in Discount (<50%); Shorts strictly in Premium (>50%).
- True Displacement on M5 (body ratio >= 60%, range >= 1.2x ATR).
- Market Structure Shift (MSS) of confirmed opposing swing.
- Anti-Chasing Guard: If price reached >= 50% toward TP before fill, cancel order.
- Breakeven Protection: Trailed to Entry at +1.0R.
- Full TP at 1.8R.
- All slippage, spread, and commissions deducted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.setups import c22_silver_bullet as sb
from v17.setups.c22_silver_bullet import (
    BODY_RATIO_MIN,
    MAX_TARGET_R,
    MIN_RR,
    NY,
    PIVOT_LEFT,
    PIVOT_RIGHT,
    RANGE_ATR_MULT,
    SESSION_ENDS,
    SPECS,
    SPREAD_BUFFER_MULT,
    WINDOWS,
    Bars,
    DayContext,
    M5Bars,
    Spec,
    build_daily_df,
    build_m5,
    compute_day_context,
    latest_confirmed_pivot,
    pivot_flags,
)

START_DATE = "2015-01-01"
END_DATE = "2020-12-31"
YEARS = list(range(2015, 2021))

# Calibrate historical specs for 2015-2020 price scale
HISTORICAL_SPECS = {
    "EURUSD": SPECS["EURUSD"],
    "GBPUSD": SPECS["GBPUSD"],
    "USA500IDXUSD": SPECS["USA500IDXUSD"],
    "XAUUSD": Spec(min_stop=1.00, max_stop=8.00, slip=0.15, commission_rt=0.00),
}


def load_parquet_symbol(sym: str, years: list[int]) -> pd.DataFrame:
    """Load local M1 parquet bars for 2015-2020."""
    dfs = []
    p1 = REPO / "data" / "parquet" / sym / "1m"
    if p1.exists():
        for y in years:
            yp = p1 / f"year={y}"
            if yp.exists():
                dfs.append(pd.read_parquet(yp))
        if dfs:
            df = pd.concat(dfs, ignore_index=True)
            df = df.rename(columns={"open": "bid_o", "high": "bid_h", "low": "bid_l", "close": "bid_c"})
            # df['ts'] is datetime64[us, UTC] -> convert to nanoseconds
            df["ts_utc"] = df["ts"].astype("int64") * 1000
            pip = 0.0001
            df["ask_o"] = df["bid_o"] + pip * 0.3
            df["ask_h"] = df["bid_h"] + pip * 0.3
            df["ask_l"] = df["bid_l"] + pip * 0.3
            df["ask_c"] = df["bid_c"] + pip * 0.3
            return df

    p2 = REPO / "data" / "bars_m1_paired" / sym
    if p2.exists():
        for y in years:
            yp = p2 / f"year={y}"
            if yp.exists():
                dfs.append(pd.read_parquet(yp))
        if dfs:
            df = pd.concat(dfs, ignore_index=True)
            # Already in ns
            return df

    return pd.DataFrame()


def load_mt5_symbol(sym: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    """Fetch M1 bars directly from MT5 terminal history."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return pd.DataFrame()
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, start_dt, end_dt)
        mt5.shutdown()
        if rates is None or len(rates) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["ts_utc"] = (df["time"] - 7200).astype(np.int64) * 1_000_000_000
        point = 0.01 if "XAU" in sym else 0.00001
        spread = df["spread"] * point
        df["bid_o"] = df["open"].astype(np.float64)
        df["bid_h"] = df["high"].astype(np.float64)
        df["bid_l"] = df["low"].astype(np.float64)
        df["bid_c"] = df["close"].astype(np.float64)

        df["ask_o"] = df["bid_o"] + spread
        df["ask_h"] = df["bid_h"] + spread
        df["ask_l"] = df["bid_l"] + spread
        df["ask_c"] = df["bid_c"] + spread
        return df
    except Exception as e:
        print(f"MT5 fetch error for {sym}: {e}")
        return pd.DataFrame()


def find_setup_institutional(
    m5: M5Bars,
    ph5: np.ndarray,
    pl5: np.ndarray,
    m5_start_idx: int,
    m5_end_idx: int,
    ctx: DayContext,
    sp: Spec,
    current_spread: float,
    intra_high: float,
    intra_low: float,
) -> sb.Setup | None:
    """Finds setup enforcing the Institutional Dealing Range Equilibrium Guard."""
    if ctx.dol_side == 0 or ctx.adr_exhausted:
        return None

    target_side = ctx.dol_side
    dealing_mid = (intra_high + intra_low) / 2.0

    for k in range(m5_start_idx, m5_end_idx):
        if not np.isfinite(m5.atr[k]) or m5.atr[k] <= 0:
            continue

        # 1. Sweep verification
        if target_side == 1:
            pivot_idx = latest_confirmed_pivot(pl5, k, right=PIVOT_RIGHT)
            if pivot_idx < 0 or not (m5.l[k] < m5.l[pivot_idx]):
                continue
            anchor_px = m5.l[k]
        else:
            pivot_idx = latest_confirmed_pivot(ph5, k, right=PIVOT_RIGHT)
            if pivot_idx < 0 or not (m5.h[k] > m5.h[pivot_idx]):
                continue
            anchor_px = m5.h[k]

        # 2. Unified Displacement & MSS
        for k2 in range(k + 1, min(k + 6, m5_end_idx)):
            rng2 = m5.h[k2] - m5.l[k2]
            if rng2 <= 0:
                continue
            body2 = abs(m5.c[k2] - m5.o[k2])
            if body2 / rng2 < BODY_RATIO_MIN or rng2 < RANGE_ATR_MULT * m5.atr[k2 - 1]:
                continue

            if target_side == 1:
                opp_pivot = latest_confirmed_pivot(ph5, k2, right=PIVOT_RIGHT)
                if opp_pivot < 0 or opp_pivot < pivot_idx or not (m5.c[k2] > m5.h[opp_pivot]):
                    continue
                anchor_px = min(anchor_px, float(np.min(m5.l[k:k2 + 1])))
            else:
                opp_pivot = latest_confirmed_pivot(pl5, k2, right=PIVOT_RIGHT)
                if opp_pivot < 0 or opp_pivot < pivot_idx or not (m5.c[k2] < m5.l[opp_pivot]):
                    continue
                anchor_px = max(anchor_px, float(np.max(m5.h[k:k2 + 1])))

            # 3. FVG on k3
            k3 = k2 + 1
            if k3 >= len(m5.o):
                continue
            k1 = k2 - 1

            if target_side == 1:
                if not (m5.l[k3] > m5.h[k1]):
                    continue
                entry_px = m5.h[k1]
                sl_px = anchor_px - SPREAD_BUFFER_MULT * current_spread
                risk_dist = entry_px - sl_px
                # Equilibrium guard: Buying strictly in Discount
                if entry_px > dealing_mid:
                    continue
            else:
                if not (m5.h[k3] < m5.l[k1]):
                    continue
                entry_px = m5.l[k1]
                sl_px = anchor_px + SPREAD_BUFFER_MULT * current_spread
                risk_dist = sl_px - entry_px
                # Equilibrium guard: Selling strictly in Premium
                if entry_px < dealing_mid:
                    continue

            if risk_dist < sp.min_stop or risk_dist > sp.max_stop:
                continue

            tp_px = entry_px + target_side * (1.80 * risk_dist)
            rr = abs(tp_px - entry_px) / risk_dist
            if rr < MIN_RR:
                continue

            return sb.Setup(
                side=target_side,
                sweep_m5=k,
                anchor_px=anchor_px,
                c3_m5=k3,
                c3_close_m1=int(m5.m1_end_idx[k3]),
                entry_px=entry_px,
                sl_px=sl_px,
                tp_px=tp_px,
                risk_dist=risk_dist,
                rr=rr,
            )

    return None


def execute_trade_breakeven(
    fill_i: int,
    session_end_i: int,
    side: int,
    sl_px: float,
    tp_px: float,
    entry_px: float,
    risk_dist: float,
    bid_o: np.ndarray,
    bid_h: np.ndarray,
    bid_l: np.ndarray,
    bid_c: np.ndarray,
    ask_o: np.ndarray,
    ask_h: np.ndarray,
    ask_l: np.ndarray,
    ask_c: np.ndarray,
) -> tuple[int, int, float]:
    """Execute on M1 with Breakeven trigger at +1.0R unrealized profit."""
    cur_sl = sl_px
    be_active = False

    for m in range(fill_i, session_end_i + 1):
        if side == 1:
            # Long position
            # 1. Check +1.0R Breakeven trigger
            if not be_active and (bid_h[m] - entry_px) >= 1.0 * risk_dist:
                cur_sl = entry_px  # Breakeven
                be_active = True

            # 2. Check Stop Loss
            if bid_l[m] <= cur_sl:
                exit_px = min(bid_o[m], cur_sl) if bid_o[m] <= cur_sl else cur_sl
                reason = 4 if be_active else 1  # 4 = Breakeven exit, 1 = Stop Loss
                return m, reason, exit_px

            # 3. Check Take Profit (1.8R)
            if bid_h[m] >= tp_px:
                exit_px = max(bid_o[m], tp_px) if bid_o[m] >= tp_px else tp_px
                return m, 2, exit_px
        else:
            # Short position
            # 1. Check +1.0R Breakeven trigger
            if not be_active and (entry_px - ask_l[m]) >= 1.0 * risk_dist:
                cur_sl = entry_px  # Breakeven
                be_active = True

            # 2. Check Stop Loss
            if ask_h[m] >= cur_sl:
                exit_px = max(ask_o[m], cur_sl) if ask_o[m] >= cur_sl else cur_sl
                reason = 4 if be_active else 1
                return m, reason, exit_px

            # 3. Check Take Profit (1.8R)
            if ask_l[m] <= tp_px:
                exit_px = min(ask_o[m], tp_px) if ask_o[m] <= tp_px else tp_px
                return m, 2, exit_px

    # Session Close Exit
    exit_px = bid_c[session_end_i] if side == 1 else ask_c[session_end_i]
    return session_end_i, 3, exit_px


def run_institutional_backtest(
    b: Bars,
    symbol: str,
    window: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Executes backtest for a symbol and session window."""
    m5 = build_m5(b)
    ph5, pl5 = pivot_flags(m5.h, m5.l, PIVOT_LEFT, PIVOT_RIGHT)
    daily_df = build_daily_df(b)
    sp = HISTORICAL_SPECS[symbol]

    (sh, sm), (eh, em) = WINDOWS[window]
    (end_h, end_m) = SESSION_ENDS[window]

    days = pd.date_range(start_date, end_date, freq="B")
    trades = []

    for day in days:
        d = day.date()
        ctx = compute_day_context(b, d, window, daily_df)
        if ctx is None or ctx.dol_side == 0 or ctx.adr_exhausted:
            continue

        d0_ns = pd.Timestamp(d).tz_localize(NY).tz_convert("UTC").value
        ws_ns = d0_ns + (sh * 3600 + sm * 60) * 1_000_000_000
        we_ns = d0_ns + (eh * 3600 + em * 60) * 1_000_000_000
        sess_end_ns = d0_ns + (end_h * 3600 + end_m * 60) * 1_000_000_000

        # Day slice for equilibrium calculation
        i_day_start = np.searchsorted(b.ts, d0_ns)
        i_ws = np.searchsorted(b.ts, ws_ns)
        if i_ws <= i_day_start + 10:
            continue
        intra_high = float(np.max(b.mid_h[i_day_start:i_ws]))
        intra_low = float(np.min(b.mid_l[i_day_start:i_ws]))

        m5_start = int(np.searchsorted(m5.ts_start, ws_ns))
        m5_end = int(np.searchsorted(m5.ts_close, we_ns))
        if m5_end <= m5_start + 2:
            continue

        cur_spread = float(b.ask_c[i_ws] - b.bid_c[i_ws]) if i_ws < len(b.ts) else sp.slip * 2

        setup = find_setup_institutional(m5, ph5, pl5, m5_start, m5_end, ctx, sp, cur_spread, intra_high, intra_low)
        if setup is None:
            continue

        # Look for fill
        m1_start_fill = setup.c3_close_m1 + 1
        m1_sess_end = int(np.searchsorted(b.ts, sess_end_ns)) - 1
        if m1_sess_end <= m1_start_fill:
            continue

        fill_i = -1
        dist_to_tp = abs(setup.tp_px - setup.entry_px)

        for m in range(m1_start_fill, m1_sess_end):
            # Anti-chasing: If price reached >= 50% toward TP before filling, cancel order
            if setup.side == 1:
                if b.bid_h[m] >= setup.entry_px + 0.50 * dist_to_tp:
                    break
                if b.bid_l[m] <= setup.anchor_px:
                    break
                if b.ask_l[m] <= setup.entry_px:
                    fill_i = m
                    break
            else:
                if b.ask_l[m] <= setup.entry_px - 0.50 * dist_to_tp:
                    break
                if b.ask_h[m] >= setup.anchor_px:
                    break
                if b.bid_h[m] >= setup.entry_px:
                    fill_i = m
                    break

        if fill_i < 0:
            continue

        # Execute trade with Breakeven protection
        exit_i, reason, exit_px = execute_trade_breakeven(
            fill_i,
            m1_sess_end,
            setup.side,
            setup.sl_px,
            setup.tp_px,
            setup.entry_px,
            setup.risk_dist,
            b.bid_o,
            b.bid_h,
            b.bid_l,
            b.bid_c,
            b.ask_o,
            b.ask_h,
            b.ask_l,
            b.ask_c,
        )

        realized_r = sb.net_r(setup.side, setup.entry_px, exit_px, reason, setup.risk_dist, sp)

        trades.append({
            "day": d,
            "year": d.year,
            "symbol": symbol,
            "window": window,
            "side": setup.side,
            "entry": setup.entry_px,
            "sl": setup.sl_px,
            "tp": setup.tp_px,
            "exit": exit_px,
            "reason": reason,
            "realized_r": realized_r,
            "risk_dist": setup.risk_dist,
        })

    return pd.DataFrame(trades)


def compute_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "wins": 0, "losses": 0, "be_count": 0, "win_rate": 0.0, "pf": 0.0, "net_r": 0.0, "max_dd_r": 0.0, "expectancy_r": 0.0}
    r = trades["realized_r"].to_numpy()
    wins = r > 0.05
    losses = r < -0.05
    breakevens = (~wins) & (~losses)
    n = len(r)
    n_w = int(np.sum(wins))
    n_l = int(np.sum(losses))
    n_be = int(np.sum(breakevens))
    wr = (n_w / (n_w + n_l) * 100.0) if (n_w + n_l) > 0 else 0.0

    gross_profit = float(np.sum(r[wins]))
    gross_loss = float(abs(np.sum(r[losses])))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    net_r = float(np.sum(r))

    eq = np.cumsum(r)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    return {
        "trades": n,
        "wins": n_w,
        "losses": n_l,
        "be_count": n_be,
        "win_rate": wr,
        "pf": pf,
        "net_r": net_r,
        "max_dd_r": max_dd,
        "expectancy_r": net_r / n if n > 0 else 0.0,
    }


def main():
    print("=" * 80)
    print("INSTITUTIONAL SILVER BULLET: 2015-2020 6-YEAR BACKTEST")
    print("Instruments: EURUSD, GBPUSD, USA500IDXUSD (US500), XAUUSD (Gold)")
    print("Enforcing: Dealing Range Equilibrium + Breakeven (+1.0R) + Anti-Chasing")
    print("=" * 80)

    # 1. Load data
    data_dict = {}

    print("\n[1/4] Loading EURUSD (2015-2020)...")
    df_eur = load_parquet_symbol("EURUSD", YEARS)
    if not df_eur.empty:
        data_dict["EURUSD"] = sb.prepare(df_eur)
        print(f"  EURUSD prepared: {len(data_dict['EURUSD'].ts):,} M1 bars.")

    print("\n[2/4] Loading GBPUSD (2015-2020)...")
    df_gbp = load_parquet_symbol("GBPUSD", YEARS)
    if not df_gbp.empty:
        data_dict["GBPUSD"] = sb.prepare(df_gbp)
        print(f"  GBPUSD prepared: {len(data_dict['GBPUSD'].ts):,} M1 bars.")

    print("\n[3/4] Loading USA500IDXUSD (2015-2020)...")
    df_spx = load_parquet_symbol("USA500IDXUSD", YEARS)
    if not df_spx.empty:
        data_dict["USA500IDXUSD"] = sb.prepare(df_spx)
        print(f"  USA500IDXUSD prepared: {len(data_dict['USA500IDXUSD'].ts):,} M1 bars.")

    print("\n[4/4] Loading XAUUSD (2015-2020 from MT5)...")
    t0 = datetime(2015, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2021, 1, 1, tzinfo=timezone.utc)
    df_xau = load_mt5_symbol("XAUUSD", t0, t1)
    if not df_xau.empty:
        data_dict["XAUUSD"] = sb.prepare(df_xau)
        print(f"  XAUUSD prepared: {len(data_dict['XAUUSD'].ts):,} M1 bars.")
    else:
        print("  XAUUSD: MT5 history unavailable or incomplete.")

    # 2. Run Backtest
    all_trades = []
    symbol_configs = [
        ("EURUSD", "AM"),
        ("EURUSD", "LDN"),
        ("GBPUSD", "LDN"),
        ("USA500IDXUSD", "AM"),
    ]
    if "XAUUSD" in data_dict:
        symbol_configs.append(("XAUUSD", "AM"))

    results = []
    print("\n" + "=" * 80)
    print("RUNNING INSTITUTIONAL BACKTEST ENGINE...")
    print("=" * 80)

    for sym, win in symbol_configs:
        if sym not in data_dict:
            continue
        print(f"\nExecuting {sym} ({win} Session)...")
        b = data_dict[sym]
        trades_df = run_institutional_backtest(b, sym, win, START_DATE, END_DATE)
        m = compute_metrics(trades_df)
        results.append({"Symbol": sym, "Window": win, **m})
        if not trades_df.empty:
            all_trades.append(trades_df)
            print(f"  Trades: {m['trades']} | Win Rate: {m['win_rate']:.1f}% | PF: {m['pf']:.2f} | Net R: +{m['net_r']:.2f}R | Max DD: {m['max_dd_r']:.2f}R | BEs: {m['be_count']}")

    # 3. Year-by-Year Breakdown
    if all_trades:
        combined_df = pd.concat(all_trades, ignore_index=True).sort_values("day")
        out_file = REPO / "out" / "backtest_2015_2020_trades.csv"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        combined_df.to_csv(out_file, index=False)
        print(f"\n[SAVED] All trades saved to {out_file}")

        print("\n" + "=" * 80)
        print("COMBINED PORTFOLIO PERFORMANCE BY YEAR (2015 - 2020)")
        print("=" * 80)
        for y in YEARS:
            sub = combined_df[combined_df["year"] == y]
            ym = compute_metrics(sub)
            print(f"Year {y}: Trades={ym['trades']:2d} | Win Rate={ym['win_rate']:5.1f}% | PF={ym['pf']:5.2f} | Net R={ym['net_r']:+6.2f}R | Max DD={ym['max_dd_r']:4.2f}R | BEs={ym['be_count']}")

        total_m = compute_metrics(combined_df)
        print("\n" + "=" * 80)
        print("COMBINED PORTFOLIO TOTAL SUMMARY (2015 - 2020)")
        print(f"Total Trades:        {total_m['trades']}")
        print(f"Wins / Losses / BE:  {total_m['wins']} Wins / {total_m['losses']} Losses / {total_m['be_count']} Breakeven")
        print(f"Win Rate:            {total_m['win_rate']:.1f}% (excluding BE)")
        print(f"Profit Factor:       {total_m['pf']:.2f}")
        print(f"Net Realized R:      +{total_m['net_r']:.2f} R")
        print(f"Max Peak-to-Valley:  {total_m['max_dd_r']:.2f} R")
        print(f"Expectancy:          +{total_m['expectancy_r']:.2f} R per trade")
        print("=" * 80)


if __name__ == "__main__":
    main()
