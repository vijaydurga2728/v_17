from __future__ import annotations

import pandas as pd

from v17.common.timeframes import pandas_offset
from v17.common.types import TF


def resample(df_1m: pd.DataFrame, tf: TF) -> pd.DataFrame:
    if tf == TF.M1:
        return df_1m.copy()
    offset = pandas_offset(tf)
    g = df_1m.set_index("ts").resample(offset, label="left", closed="left")
    out = pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "volume": g["volume"].sum(min_count=1),
            "spread_pips": g["spread_pips"].mean(),
        }
    ).dropna(subset=["open"]).reset_index()
    out["volume"] = out["volume"].astype("int64")
    return out


def resample_paired(df_1m: pd.DataFrame, tf: TF) -> pd.DataFrame:
    """Resample paired bid/ask M1 bars (ts_utc, bid_*, ask_*, *_volume, spread_mid) to a higher TF.

    Expected input columns: ts_utc (int64 ns), symbol, bid_o, bid_h, bid_l, bid_c,
    ask_o, ask_h, ask_l, ask_c, bid_volume, ask_volume, spread_mid.
    """
    if tf == TF.M1:
        return df_1m.copy().reset_index(drop=True)
    if "ts_utc" not in df_1m.columns:
        raise ValueError("resample_paired expects 'ts_utc' column (int64 ns)")
    offset = pandas_offset(tf)
    df = df_1m.copy()
    df["_ts"] = pd.to_datetime(df["ts_utc"], unit="ns", utc=True)
    df = df.set_index("_ts").sort_index()
    g = df.resample(offset, label="left", closed="left")
    out = pd.DataFrame({
        "bid_o": g["bid_o"].first(),
        "bid_h": g["bid_h"].max(),
        "bid_l": g["bid_l"].min(),
        "bid_c": g["bid_c"].last(),
        "ask_o": g["ask_o"].first(),
        "ask_h": g["ask_h"].max(),
        "ask_l": g["ask_l"].min(),
        "ask_c": g["ask_c"].last(),
        "bid_volume": g["bid_volume"].sum(min_count=1),
        "ask_volume": g["ask_volume"].sum(min_count=1),
        "spread_mid": g["spread_mid"].mean(),
    }).dropna(subset=["bid_o"]).reset_index()
    out["ts_utc"] = out["_ts"].astype("int64")
    out = out.drop(columns=["_ts"])
    if "symbol" in df_1m.columns:
        out.insert(1, "symbol", df_1m["symbol"].iloc[0])
    front = ["ts_utc"] + (["symbol"] if "symbol" in out.columns else [])
    rest = [c for c in out.columns if c not in front]
    return out[front + rest]
