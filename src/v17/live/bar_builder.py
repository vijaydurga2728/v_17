from __future__ import annotations

from datetime import datetime

import pandas as pd

from v17.common.dtos import Bar, Tick
from v17.common.types import TF, Symbol
from v17.mt5.protocol import TradeGateway

_REQUIRED_TFS: tuple[TF, ...] = (TF.D1, TF.H4, TF.M15, TF.M1)
_BARS_LOOKBACK: int = 200
_MIN_BARS: int = 20


def bars_to_df(bars: list[Bar]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts": pd.Timestamp(b.ts),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": b.volume,
            }
            for b in bars
        ]
    )


class BarBuilder:
    """Detects new 1m bar boundaries and fetches fresh rates for all TFs."""

    def __init__(self, symbol: Symbol) -> None:
        self._symbol = symbol
        self._last_m1_ts: datetime | None = None

    def on_tick(
        self, tick: Tick, gateway: TradeGateway
    ) -> dict[TF, pd.DataFrame] | None:
        bar_minute = tick.ts.replace(second=0, microsecond=0)
        if self._last_m1_ts is None:
            self._last_m1_ts = bar_minute
            return None
        if bar_minute <= self._last_m1_ts:
            return None
        self._last_m1_ts = bar_minute
        result: dict[TF, pd.DataFrame] = {}
        for tf in _REQUIRED_TFS:
            bars = gateway.rates(self._symbol, tf, _BARS_LOOKBACK)
            if len(bars) < _MIN_BARS:
                return None
            result[tf] = bars_to_df(bars)
        return result
