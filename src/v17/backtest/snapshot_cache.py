from __future__ import annotations

from datetime import timedelta

import pandas as pd

from v17.backtest.fast_choch import detect_choch_fast
from v17.common.dtos import Swing
from v17.common.types import Side


def precompute_daily_ema20(bars_1d: pd.DataFrame) -> pd.Series:
    ema = bars_1d["close"].ewm(span=20, adjust=False).mean()
    return pd.Series(ema.to_numpy(), index=pd.to_datetime(bars_1d["ts"]), name="ema20")


def precompute_1m_choches(bars_1m: pd.DataFrame) -> list[Swing]:
    return detect_choch_fast(bars_1m, swing_window=3)


def precompute_daily_pdhl_sweeps(
    bars_1d: pd.DataFrame,
) -> list[tuple[pd.Timestamp, Side]]:
    """Return per-day PDH/PDL liquidity-raid signals (ICT doctrine).

    ICT definition (no-lookahead, R1 compliant):
      PDH sweep (bearish): today's wick HIGH > previous day's HIGH,
                           but today's CLOSE < previous day's HIGH.
                           → Smart money raided buy-side liquidity above PDH,
                             filled sell orders, rejected. Intraday intent = BEAR.
      PDL sweep (bullish): today's wick LOW  < previous day's LOW,
                           but today's CLOSE > previous day's LOW.
                           → Smart money raided sell-side liquidity below PDL,
                             filled buy orders, rejected. Intraday intent = BULL.

    The returned datetime key is (sweep_bar_ts + 1 trading day) so that
    snapshot_at() can match it against today_start without lookahead.

    When BOTH sweeps occur on the same bar (rare: e.g. outside-day reversal),
    the larger magnitude sweep wins (absolute distance from previous extreme).

    Args:
        bars_1d: Daily OHLCV dataframe with 'ts','high','low','close' columns.
                 ts must be UTC-aware. Rows must be sorted ascending by ts.

    Returns:
        List of (usable_date, Side) sorted ascending by usable_date.
        usable_date = the next day's midnight UTC (today_start of the day
        that can USE this sweep as a bias signal).
    """
    if len(bars_1d) < 2:
        return []

    df = bars_1d.reset_index(drop=True)
    prev_high = df["high"].shift(1)
    prev_low = df["low"].shift(1)

    # ICT: wick through + close rejection (NOT a breakout)
    pdh_swept: pd.Series = (df["high"] > prev_high) & (df["close"] < prev_high)
    pdl_swept: pd.Series = (df["low"] < prev_low) & (df["close"] > prev_low)

    results: list[tuple[pd.Timestamp, Side]] = []
    for idx in df.index[1:]:  # skip first row (no previous bar)
        swept_pdh = bool(pdh_swept.iloc[idx])
        swept_pdl = bool(pdl_swept.iloc[idx])
        if not swept_pdh and not swept_pdl:
            continue

        bar_ts: pd.Timestamp = pd.Timestamp(df["ts"].iloc[idx])
        # Key for snapshot_at: the NEXT calendar day's midnight UTC
        usable_date = bar_ts.normalize() + timedelta(days=1)

        if swept_pdh and swept_pdl:
            # Outside-day reversal — take the larger magnitude raid
            ph_distance = float(df["high"].iloc[idx]) - float(prev_high.iloc[idx])
            pl_distance = float(prev_low.iloc[idx]) - float(df["low"].iloc[idx])
            side = Side.SELL if ph_distance >= pl_distance else Side.BUY
        elif swept_pdh:
            side = Side.SELL
        else:
            side = Side.BUY

        results.append((usable_date, side))

    return results
