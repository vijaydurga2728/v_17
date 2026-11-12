"""Integration tests for the Cycle 6 backtest orchestrator.

Calibration note (deviation from brief):
    The brief's _synthetic_m5 helper sets bid_o == bid_c == close on every bar,
    producing zero-body candles. The micro-trigger requires body >= confirm_body_mult
    * ATR, so no confirm signals ever fire and the trade log stays empty.

    Fix: use the *previous* bar's close as the current bar's open. This creates
    realistic bodies while preserving the brief's random-seed determinism contract.
    Scale is also increased to 2× pip so ATR is comfortably exceeded on trending
    bars. All other logic and assertions are verbatim from the brief.
"""
import numpy as np
import pandas as pd

from v17.backtest.c6_runner import run_backtest


def _synthetic_m5(n_days: int, trend: float, pair: str, start_date: str = "2020-01-02"):
    rows = []
    close = 100.0 if pair == "USA500IDXUSD" else (0.7000 if pair == "AUDUSD" else 110.0)
    # 2x pip scale so ATR is non-trivial; open = prev close so bodies are non-zero.
    scale = 2.0 if pair == "USA500IDXUSD" else (0.0002 if pair == "AUDUSD" else 0.02)
    rng = np.random.default_rng(42 + hash(pair) % 1000)
    prev_close = close
    for d in range(n_days):
        date = pd.Timestamp(start_date, tz="UTC") + pd.Timedelta(days=d)
        for i in range(12 * 10):  # 10 trading hours, 12 M5 bars per hour
            ts = date + pd.Timedelta(hours=8) + pd.Timedelta(minutes=5 * i)
            noise = rng.normal(0, scale)
            new_close = prev_close + trend * scale + noise
            open_ = prev_close
            hi = max(open_, new_close) + scale * 0.1
            lo = min(open_, new_close) - scale * 0.1
            rows.append({
                "ts_utc": ts.value, "symbol": pair,
                "bid_o": open_, "bid_h": hi, "bid_l": lo, "bid_c": new_close,
                "ask_o": open_ + scale * 0.05, "ask_h": hi + scale * 0.05,
                "ask_l": lo + scale * 0.05, "ask_c": new_close + scale * 0.05,
                "bid_volume": 100, "ask_volume": 100, "spread_mid": scale * 0.05,
            })
            prev_close = new_close
    return pd.DataFrame(rows)


def test_runner_emits_trades_and_curve():
    spx = _synthetic_m5(5, trend=0.1, pair="USA500IDXUSD")
    aud = _synthetic_m5(5, trend=0.1, pair="AUDUSD")
    jpy = _synthetic_m5(5, trend=0.1, pair="USDJPY")
    cal = pd.DataFrame({"ts_utc": [], "currency": [], "impact": [], "title": []})
    tl, ec = run_backtest(
        spx_m5=spx, fx_m5_by_sym={"AUDUSD": aud, "USDJPY": jpy},
        calendar_idx=cal, params={"K": 0.3, "slope_window": 12, "C": 0.4},
        initial_equity=10_000.0,
        start_ts_ns=spx["ts_utc"].min(), end_ts_ns=spx["ts_utc"].max(),
    )
    # With 5 days + rising regime, expect at least some trades.
    assert len(ec) > 0
    assert "equity" in ec.columns
    assert ec["equity"].iloc[0] == 10_000.0
    assert set(["trade_id", "symbol", "side", "entry_ts_ns", "net_pnl_usd"]).issubset(tl.columns)


def test_runner_determinism():
    spx = _synthetic_m5(3, trend=0.1, pair="USA500IDXUSD")
    aud = _synthetic_m5(3, trend=0.1, pair="AUDUSD")
    jpy = _synthetic_m5(3, trend=0.1, pair="USDJPY")
    cal = pd.DataFrame({"ts_utc": [], "currency": [], "impact": [], "title": []})
    params = {"K": 0.3, "slope_window": 12, "C": 0.4}
    tl1, ec1 = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params,
                             10_000.0, spx["ts_utc"].min(), spx["ts_utc"].max())
    tl2, ec2 = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params,
                             10_000.0, spx["ts_utc"].min(), spx["ts_utc"].max())
    pd.testing.assert_frame_equal(tl1, tl2)
    pd.testing.assert_frame_equal(ec1, ec2)
