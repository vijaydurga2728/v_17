from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from v17.backtest.snapshot_cache import precompute_daily_pdhl_sweeps
from v17.common.types import Bias, Side
from v17.structure.bias import compute_bias, compute_bias_fast


def _bars_1d(closes: list[float], start: datetime) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(closes):
        ts = start + timedelta(days=i)
        rows.append({"ts": ts, "open": c, "high": c + 0.001, "low": c - 0.001, "close": c, "volume": 1, "spread_pips": 0.0})
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def _bars_4h(n: int, start: str) -> pd.DataFrame:
    """Build n 4h bars with drift and sine oscillation to create swings."""
    ts = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    base = 1.10 + np.linspace(0, 0.01, n) + np.sin(np.arange(n) / 7) * 0.001
    return pd.DataFrame(
        {
            "ts": ts,
            "open": base,
            "high": base + 0.0005,
            "low": base - 0.0005,
            "close": base,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.8),
        }
    )


class TestBiasAtSwingLength3:
    def test_short_history_produces_bias_not_none(self) -> None:
        # 60 days of 1d bars (all >=20 for EMA) + 240 4h bars with drift+sine
        # swing_length=3 detects more swings than swing_length=10
        start_dt = datetime(2024, 1, 1, tzinfo=UTC)
        df_1d = _bars_1d([1.10 + i * 0.001 for i in range(60)], start_dt)
        df_4h = _bars_4h(240, "2024-01-01")
        bias = compute_bias(df_1d, df_4h)
        # With swing_length=3 on clean oscillating 4h data, we must detect >=1 swing.
        # The last swing will either align or not with daily bias, but either way
        # it should not all be NONE due to missing swings.
        assert bias != Bias.NONE


# ---------------------------------------------------------------------------
# compute_bias_fast — PDH/PDL branch tests
# ---------------------------------------------------------------------------

EMA = Decimal("1.1000")


class TestComputeBiasFastPDHL:
    """ICT PDH/PDL sweep gates on compute_bias_fast."""

    def test_pdl_sweep_bull_with_4h_buy_returns_bull(self) -> None:
        """PDL swept yesterday + 4H swing BUY -> BULL bias (discount long)."""
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.0950"),  # below EMA -- classic discount
            last_4h_swing_side=Side.BUY,
            pdh_pdl_side=Side.BUY,
        )
        assert bias == Bias.BULL

    def test_pdh_sweep_bear_with_4h_sell_returns_bear(self) -> None:
        """PDH swept yesterday + 4H swing SELL -> BEAR bias (premium short)."""
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.1050"),  # above EMA -- classic premium
            last_4h_swing_side=Side.SELL,
            pdh_pdl_side=Side.SELL,
        )
        assert bias == Bias.BEAR

    def test_pdh_sweep_mismatch_falls_through_to_ema(self) -> None:
        """PDH swept (bear intent) + 4H BUY: mismatch falls through to EMA20
        fallback. close > EMA + 4H BUY → BULL via EMA path (not NONE).
        """
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.1050"),
            last_4h_swing_side=Side.BUY,
            pdh_pdl_side=Side.SELL,
        )
        assert bias == Bias.BULL

    def test_pdl_sweep_mismatch_falls_through_to_ema(self) -> None:
        """PDL swept (bull intent) + 4H SELL: mismatch falls through to EMA20
        fallback. close < EMA + 4H SELL → BEAR via EMA path (not NONE).
        """
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.0950"),
            last_4h_swing_side=Side.SELL,
            pdh_pdl_side=Side.BUY,
        )
        assert bias == Bias.BEAR

    def test_pdh_sweep_mismatch_ema_also_disagrees_returns_none(self) -> None:
        """Mismatch + EMA fallback also fails to align → NONE (true conflict)."""
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.1050"),  # price above EMA (bull)
            last_4h_swing_side=Side.SELL,  # 4H bearish
            pdh_pdl_side=Side.BUY,         # PDL swept (bullish)
        )
        assert bias == Bias.NONE

    def test_no_sweep_fallback_ema_bull(self) -> None:
        """No PDH/PDL sweep -> original EMA20 + 4H logic (bull case)."""
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.1050"),
            last_4h_swing_side=Side.BUY,
            pdh_pdl_side=None,
        )
        assert bias == Bias.BULL

    def test_no_sweep_fallback_ema_bear(self) -> None:
        """No PDH/PDL sweep -> original EMA20 + 4H logic (bear case)."""
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.0950"),
            last_4h_swing_side=Side.SELL,
            pdh_pdl_side=None,
        )
        assert bias == Bias.BEAR

    def test_require_htf_sweep_blocks_without_sweep(self) -> None:
        """When require_htf_sweep=True, no PDH/PDL sweep -> NONE (no inside-day trades)."""
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.1050"),
            last_4h_swing_side=Side.BUY,
            pdh_pdl_side=None,
            require_htf_sweep=True,
        )
        assert bias == Bias.NONE

    def test_require_htf_sweep_allows_with_sweep(self) -> None:
        """When require_htf_sweep=True, matching PDH/PDL sweep -> BULL."""
        bias = compute_bias_fast(
            ema20_at=EMA,
            last_close=Decimal("1.0950"),
            last_4h_swing_side=Side.BUY,
            pdh_pdl_side=Side.BUY,
            require_htf_sweep=True,
        )
        assert bias == Bias.BULL

    def test_no_4h_swing_always_returns_none(self) -> None:
        """4H swing is prerequisite -- if missing, bias is NONE regardless of sweep."""
        for pdhl in (Side.BUY, Side.SELL, None):
            assert (
                compute_bias_fast(
                    ema20_at=EMA,
                    last_close=Decimal("1.1050"),
                    last_4h_swing_side=None,
                    pdh_pdl_side=pdhl,
                )
                == Bias.NONE
            ), f"Expected NONE for pdh_pdl_side={pdhl} when no 4H swing"


# ---------------------------------------------------------------------------
# precompute_daily_pdhl_sweeps -- unit tests
# ---------------------------------------------------------------------------

def _make_daily_bars(
    records: list[dict[str, float]],
    start: datetime = datetime(2024, 1, 1, tzinfo=UTC),
) -> pd.DataFrame:
    """Build a daily OHLCV dataframe from a list of {o,h,l,c} dicts."""
    rows = []
    for i, r in enumerate(records):
        ts = start + timedelta(days=i)
        rows.append(
            {
                "ts": ts,
                "open": r["o"],
                "high": r["h"],
                "low": r["l"],
                "close": r["c"],
                "volume": 1,
                "spread_pips": 0.0,
            }
        )
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


class TestPrecomputeDailyPDHLSweeps:
    def test_empty_on_single_bar(self) -> None:
        df = _make_daily_bars([{"o": 1.1, "h": 1.102, "l": 1.098, "c": 1.1}])
        assert precompute_daily_pdhl_sweeps(df) == []

    def test_pdl_sweep_detected(self) -> None:
        """Day 1: low wicks below day0 low, closes above day0 low -> BUY."""
        df = _make_daily_bars(
            [
                {"o": 1.1000, "h": 1.1050, "l": 1.0950, "c": 1.1000},  # day 0 -- prev
                {"o": 1.0980, "h": 1.1010, "l": 1.0930, "c": 1.0970},  # day 1 -- PDL sweep
            ]
        )
        result = precompute_daily_pdhl_sweeps(df)
        assert len(result) == 1
        usable_date, side = result[0]
        assert side == Side.BUY
        # usable_date must be day 2 midnight UTC
        expected = pd.Timestamp(datetime(2024, 1, 3, tzinfo=UTC))
        assert usable_date == expected

    def test_pdh_sweep_detected(self) -> None:
        """Day 1: high wicks above day0 high, closes below day0 high -> SELL."""
        df = _make_daily_bars(
            [
                {"o": 1.1000, "h": 1.1050, "l": 1.0950, "c": 1.1000},  # day 0 -- prev
                {"o": 1.1020, "h": 1.1080, "l": 1.0990, "c": 1.1030},  # day 1 -- PDH sweep
            ]
        )
        result = precompute_daily_pdhl_sweeps(df)
        assert len(result) == 1
        _, side = result[0]
        assert side == Side.SELL

    def test_no_sweep_when_close_breaks_through(self) -> None:
        """If close > PDH, it's a breakout -- NOT a liquidity raid. No signal."""
        df = _make_daily_bars(
            [
                {"o": 1.1000, "h": 1.1050, "l": 1.0950, "c": 1.1000},
                {"o": 1.1020, "h": 1.1080, "l": 1.0990, "c": 1.1070},  # close above prev high
            ]
        )
        result = precompute_daily_pdhl_sweeps(df)
        assert result == []

    def test_no_sweep_when_wick_does_not_reach(self) -> None:
        """High stays below PDH -> no PDH sweep."""
        df = _make_daily_bars(
            [
                {"o": 1.1000, "h": 1.1050, "l": 1.0950, "c": 1.1000},
                {"o": 1.1000, "h": 1.1040, "l": 1.0960, "c": 1.1010},  # high below prev high
            ]
        )
        result = precompute_daily_pdhl_sweeps(df)
        assert result == []

    def test_both_swept_larger_magnitude_wins(self) -> None:
        """Outside-day with both sweeps -- larger distance wins."""
        df = _make_daily_bars(
            [
                {"o": 1.1000, "h": 1.1050, "l": 1.0950, "c": 1.1000},
                # PDH distance: 1.1090 - 1.1050 = 0.0040
                # PDL distance: 1.0950 - 1.0890 = 0.0060  -> PDL wins -> BUY
                {"o": 1.1000, "h": 1.1090, "l": 1.0890, "c": 1.1000},
            ]
        )
        result = precompute_daily_pdhl_sweeps(df)
        assert len(result) == 1
        _, side = result[0]
        assert side == Side.BUY  # PDL sweep larger

    def test_multiple_days_sorted_ascending(self) -> None:
        """Multiple sweep days must be returned sorted by usable_date.

        day0: baseline  h=1.1050 l=1.0950
        day1: PDL sweep — wick below 1.0950, close above 1.0950 -> BUY
        day2: no sweep  — stays entirely within day1 range (h<day1.h, l>day1.l)
        day3: PDH sweep — wick above day2.h=1.1010, close below day2.h -> SELL
        """
        df = _make_daily_bars(
            [
                {"o": 1.1000, "h": 1.1050, "l": 1.0950, "c": 1.1000},  # day0 baseline
                {"o": 1.0980, "h": 1.1010, "l": 1.0930, "c": 1.0970},  # day1: PDL (l<1.0950, c>1.0950)
                {"o": 1.0975, "h": 1.1000, "l": 1.0960, "c": 1.0990},  # day2: no sweep (h=1.1000 < prev_h=1.1010; l=1.0960 > prev_l=1.0930)
                {"o": 1.0995, "h": 1.1060, "l": 1.0985, "c": 1.1005},  # day3: PDH (h=1.1060>1.1000, c=1.1005 < 1.1000? NO — 1.1005>1.1000)
            ]
        )
        # Diagnose: day3 close=1.1005 > prev_h=1.1000 → NOT a sweep (breakout). Fix:
        df2 = _make_daily_bars(
            [
                {"o": 1.1000, "h": 1.1050, "l": 1.0950, "c": 1.1000},  # day0
                {"o": 1.0980, "h": 1.1010, "l": 1.0930, "c": 1.0970},  # day1: PDL sweep -> BUY
                {"o": 1.0975, "h": 1.1000, "l": 1.0960, "c": 1.0990},  # day2: no sweep
                {"o": 1.0995, "h": 1.1060, "l": 1.0985, "c": 1.0995},  # day3: PDH (h=1.1060>1.1000, c=1.0995<1.1000) -> SELL
            ]
        )
        result = precompute_daily_pdhl_sweeps(df2)
        assert len(result) == 2
        dates = [r[0] for r in result]
        assert dates == sorted(dates), "Results must be sorted ascending"
        assert result[0][1] == Side.BUY   # day1 PDL -> BUY
        assert result[1][1] == Side.SELL  # day3 PDH -> SELL
