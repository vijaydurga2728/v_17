from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from v17.common.dtos import Bar, Tick
from v17.common.types import TF, Symbol
from v17.live.bar_builder import BarBuilder, bars_to_df
from v17.mt5.fake import FakeMT5

_SYM = Symbol("EURUSD")


def _ts(h: int, m: int) -> datetime:
    return datetime(2026, 1, 6, h, m, tzinfo=UTC)


def _tick(h: int, m: int, s: int = 0) -> Tick:
    return Tick(
        symbol=_SYM,
        ts=datetime(2026, 1, 6, h, m, s, tzinfo=UTC),
        bid=Decimal("1.09990"),
        ask=Decimal("1.09998"),
    )


def _bar(i: int) -> Bar:
    base = Decimal("1.1") + Decimal(str(i)) * Decimal("0.0001")
    return Bar(
        symbol=_SYM,
        tf=TF.M1,
        ts=datetime(2026, 1, 6, 7, i % 60, tzinfo=UTC),
        open=base,
        high=base + Decimal("0.0003"),
        low=base - Decimal("0.0003"),
        close=base + Decimal("0.0001"),
    )


def _enough_bars(fake: FakeMT5, count: int = 25) -> None:
    bars = [_bar(i) for i in range(count)]
    for tf in (TF.D1, TF.H4, TF.M15, TF.M1):
        bar_tf = [
            Bar(
                symbol=_SYM,
                tf=tf,
                ts=b.ts,
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
            )
            for b in bars
        ]
        fake.set_bars(_SYM, tf, bar_tf)


class TestBarsTodf:
    def test_converts_list_to_df(self) -> None:
        bars = [_bar(0), _bar(1)]
        df = bars_to_df(bars)
        assert list(df.columns) >= ["ts", "open", "high", "low", "close"]
        assert len(df) == 2

    def test_ts_is_timestamp(self) -> None:
        df = bars_to_df([_bar(0)])
        assert isinstance(df["ts"].iloc[0], pd.Timestamp)


class TestBarBuilderSameMinute:
    def test_same_minute_returns_none(self) -> None:
        fake = FakeMT5()
        fake.connect()
        _enough_bars(fake)
        bb = BarBuilder(_SYM)
        t1 = _tick(7, 30, 0)
        t2 = _tick(7, 30, 30)
        bb.on_tick(t1, fake)  # prime last ts
        result = bb.on_tick(t2, fake)
        assert result is None


class TestBarBuilderNewMinute:
    def test_new_minute_returns_bars(self) -> None:
        fake = FakeMT5()
        fake.connect()
        _enough_bars(fake)
        bb = BarBuilder(_SYM)
        bb.on_tick(_tick(7, 30, 0), fake)  # prime
        result = bb.on_tick(_tick(7, 31, 0), fake)  # new minute
        assert result is not None
        for tf in (TF.D1, TF.H4, TF.M15, TF.M1):
            assert tf in result
            assert isinstance(result[tf], pd.DataFrame)
            assert len(result[tf]) > 0

    def test_first_tick_primes_without_returning(self) -> None:
        fake = FakeMT5()
        fake.connect()
        _enough_bars(fake)
        bb = BarBuilder(_SYM)
        result = bb.on_tick(_tick(7, 30, 0), fake)
        # First tick: primes _last_m1_ts but returns None
        assert result is None


class TestBarBuilderInsufficientBars:
    def test_too_few_bars_returns_none(self) -> None:
        fake = FakeMT5()
        fake.connect()
        # Only 5 bars — below MIN_BARS=20
        for tf in (TF.D1, TF.H4, TF.M15, TF.M1):
            fake.set_bars(_SYM, tf, [_bar(i) for i in range(5)])
        bb = BarBuilder(_SYM)
        bb.on_tick(_tick(7, 30, 0), fake)
        result = bb.on_tick(_tick(7, 31, 0), fake)
        assert result is None
