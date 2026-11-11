"""Scheduled-blackout check (Policy D of spec §12).

Policy D is DEFERRED this cycle per spec amendment 2026-11-03 (Finnhub
free-tier calendar endpoint blocked). The module stays built so the
pipeline is ready when a Dukascopy-sourced calendar lands.
"""
from __future__ import annotations

import pandas as pd

from v17.common.types import Symbol
NEWS_BLACKOUT_BEFORE_MIN = 10
NEWS_BLACKOUT_AFTER_MIN = 20

SYMBOL_CURRENCY_MAP: dict[str, list[str]] = {
    "EURUSD": ["USD", "EUR"],
    "GBPUSD": ["USD", "GBP"],
    "USATECHIDXUSD": ["USD"],
    "USA500IDXUSD": ["USD"],
    "USA30IDXUSD": ["USD"],
    "EURGBP": ["EUR", "GBP"],
    "AUDUSD": ["USD"],
    "USDCAD": ["USD"],
    "USDCHF": ["USD"],
    "NZDUSD": ["USD"],
    "USDJPY": ["USD"],
    "BTCUSD": ["USD"],
    "XAUUSD": ["USD"],
}

# Backward compatibility for providers.py (Symbol keys)
AFFECTED: dict[Symbol, set[str]] = {
    Symbol("EURUSD"): {"USD", "EUR"},
    Symbol("GBPUSD"): {"USD", "GBP"},
    Symbol("USATECHIDXUSD"): {"USD"},
    Symbol("USA500IDXUSD"): {"USD"},
    Symbol("USA30IDXUSD"): {"USD"},
    Symbol("EURGBP"): {"EUR", "GBP"},
    Symbol("AUDUSD"): {"USD"},
    Symbol("USDCAD"): {"USD"},
    Symbol("USDCHF"): {"USD"},
    Symbol("NZDUSD"): {"USD"},
    Symbol("USDJPY"): {"USD"},
    Symbol("BTCUSD"): {"USD"},
    Symbol("XAUUSD"): {"USD"},
}


_BEFORE_NS = NEWS_BLACKOUT_BEFORE_MIN * 60_000_000_000
_AFTER_NS = NEWS_BLACKOUT_AFTER_MIN * 60_000_000_000


def is_in_blackout(ts_utc_ns: int, calendar: pd.DataFrame, currencies: list[str]) -> bool:
    if calendar is None or calendar.empty:
        return False
    sub = calendar[calendar["currency"].isin(currencies)]
    if sub.empty:
        return False
    starts = sub["timestamp_utc"] - _BEFORE_NS
    ends = sub["timestamp_utc"] + _AFTER_NS
    hits = (ts_utc_ns >= starts) & (ts_utc_ns <= ends)
    return bool(hits.any())
