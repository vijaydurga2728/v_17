"""Cycle 24 Setup: HTF (H1) Order Block Tap + LTF (M5) Unmitigated FVG Confluence (Fast Sliced).

ICT Institutional Confluence Framework:
1. Higher Timeframe (H1) identifies institutional sponsorship via Order Blocks.
2. Price taps into active unmitigated HTF Order Block during active London or NY sessions.
3. Lower Timeframe (M5) reacts with an Unmitigated Displacement FVG in the direction of the OB.
4. Entry limit at proximal edge of FVG; Stop Loss at swing extreme; Target 2.0R to 3.0R.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Spec:
    min_stop: float
    max_stop: float
    slip: float
    commission_rt: float


SPECS: Final[dict[str, Spec]] = {
    "EURUSD": Spec(min_stop=0.0006, max_stop=0.0030, slip=0.00005, commission_rt=0.00006),
    "GBPUSD": Spec(min_stop=0.0010, max_stop=0.0040, slip=0.00005, commission_rt=0.00006),
    "USATECHIDXUSD": Spec(min_stop=8.0, max_stop=60.0, slip=0.5, commission_rt=0.0),
    "XAUUSD": Spec(min_stop=2.00, max_stop=12.00, slip=0.15, commission_rt=0.0),
}


@dataclass
class H1Bars:
    ts_start: np.ndarray  # UTC ns
    ts_end: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray


def build_h1(ts: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> H1Bars:
    """Aggregates 1m bars to 1h bars with exact closed timestamps using pandas floor."""
    ts_dt = pd.to_datetime(ts, unit="ns", utc=True)
    df = pd.DataFrame({"ts": ts, "o": o, "h": h, "l": l, "c": c})
    df["h1"] = ts_dt.floor("1h")
    g = df.groupby("h1").agg(
        ts_start=("ts", "first"),
        ts_end=("ts", "last"),
        o=("o", "first"),
        h=("h", "max"),
        l=("l", "min"),
        c=("c", "last"),
    )
    return H1Bars(
        g["ts_start"].to_numpy(np.int64),
        g["ts_end"].to_numpy(np.int64),
        g["o"].to_numpy(np.float64),
        g["h"].to_numpy(np.float64),
        g["l"].to_numpy(np.float64),
        g["c"].to_numpy(np.float64),
    )


def build_m5(ts: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray):
    ts_dt = pd.to_datetime(ts, unit="ns", utc=True)
    df = pd.DataFrame({"ts": ts, "o": o, "h": h, "l": l, "c": c, "m1_idx": np.arange(len(ts))})
    df["m5"] = ts_dt.floor("5min")
    g = df.groupby("m5").agg(
        ts_start=("ts", "first"),
        ts_end=("ts", "last"),
        o=("o", "first"),
        h=("h", "max"),
        l=("l", "min"),
        c=("c", "last"),
        m1_idx_end=("m1_idx", "last"),
    )
    return g


@dataclass
class ActiveOB:
    side: int          # 1 = Bullish OB, -1 = Bearish OB
    top: float
    bottom: float
    start_ns: int      # When OB candle closed


def scan_htf_ob_ltf_fvg_trades(
    b_m1_ts: np.ndarray,
    b_m1_bid_o: np.ndarray, b_m1_bid_h: np.ndarray, b_m1_bid_l: np.ndarray, b_m1_bid_c: np.ndarray,
    b_m1_ask_o: np.ndarray, b_m1_ask_h: np.ndarray, b_m1_ask_l: np.ndarray, b_m1_ask_c: np.ndarray,
    b_m1_mid_o: np.ndarray, b_m1_mid_h: np.ndarray, b_m1_mid_l: np.ndarray, b_m1_mid_c: np.ndarray,
    symbol: str,
    sp: Spec,
    start_date: str = "2021-01-01",
    end_date: str = "2024-12-31",
    target_rr: float = 2.0,
) -> pd.DataFrame:
    # 1. Build H1 bars
    h1 = build_h1(b_m1_ts, b_m1_mid_o, b_m1_mid_h, b_m1_mid_l, b_m1_mid_c)
    n_h1 = len(h1.ts_start)

    # 2. Build M5 bars
    m5_df = build_m5(b_m1_ts, b_m1_mid_o, b_m1_mid_h, b_m1_mid_l, b_m1_mid_c)
    m5_ts_start = m5_df["ts_start"].to_numpy(np.int64)
    m5_o = m5_df["o"].to_numpy(np.float64)
    m5_h = m5_df["h"].to_numpy(np.float64)
    m5_l = m5_df["l"].to_numpy(np.float64)
    m5_c = m5_df["c"].to_numpy(np.float64)
    m5_m1_end = m5_df["m1_idx_end"].to_numpy(np.int64)
    n_m5 = len(m5_ts_start)

    dt_ny = pd.to_datetime(m5_ts_start, unit="ns", utc=True).tz_convert(NY)
    dates = dt_ny.date
    hours = dt_ny.hour

    start_ts_ns = pd.Timestamp(start_date, tz="UTC").value
    end_ts_ns = pd.Timestamp(end_date + " 23:59:59", tz="UTC").value

    # Extract all H1 Order Blocks
    h1_obs: list[ActiveOB] = []
    min_ob_size = 0.0004 if "USD" in symbol else 5.0

    for k in range(2, n_h1):
        # Bullish H1 FVG: low[k] > high[k-2]
        if h1.l[k] > h1.h[k - 2] and (h1.l[k] - h1.h[k - 2]) >= min_ob_size:
            if h1.c[k - 2] < h1.o[k - 2]: # Down candle before displacement
                h1_obs.append(ActiveOB(
                    side=1,
                    top=float(h1.h[k - 2]),
                    bottom=float(h1.l[k - 2]),
                    start_ns=int(h1.ts_end[k]),
                ))

        # Bearish H1 FVG: high[k] < low[k-2]
        elif h1.h[k] < h1.l[k - 2] and (h1.l[k - 2] - h1.h[k]) >= min_ob_size:
            if h1.c[k - 2] > h1.o[k - 2]: # Up candle before displacement
                h1_obs.append(ActiveOB(
                    side=-1,
                    top=float(h1.h[k - 2]),
                    bottom=float(h1.l[k - 2]),
                    start_ns=int(h1.ts_end[k]),
                ))

    print(f"[{symbol}] Extracted {len(h1_obs)} H1 institutional Order Blocks.")

    # Convert OBs to numpy for fast vectorized lookup
    ob_starts = np.array([o.start_ns for o in h1_obs], dtype=np.int64)
    ob_sides = np.array([o.side for o in h1_obs], dtype=np.int32)
    ob_tops = np.array([o.top for o in h1_obs], dtype=np.float64)
    ob_bots = np.array([o.bottom for o in h1_obs], dtype=np.float64)

    trades: list[dict] = []
    min_fvg_m5 = 0.00010 if "USD" in symbol else 1.0
    last_trade_day = None

    for i in range(2, n_m5):
        cur_ts = m5_ts_start[i]
        if cur_ts < start_ts_ns or cur_ts > end_ts_ns:
            continue

        cur_day = str(dates[i])
        cur_hour = hours[i]

        if cur_day == last_trade_day:
            continue

        # Active Session Filter: London (02:00-05:00 NY) or NY Session (08:00-12:00 NY)
        in_session = (2 <= cur_hour < 5) or (8 <= cur_hour < 12)
        if not in_session:
            continue

        # Bullish M5 FVG
        if m5_l[i] > m5_h[i - 2] and (m5_l[i] - m5_h[i - 2]) >= min_fvg_m5:
            recent_low = min(m5_l[i], m5_l[i - 1], m5_l[i - 2])
            
            # Fast vectorized check: find available bullish OBs where recent_low tapped inside [bottom, top]
            valid_mask = (ob_starts < cur_ts) & (ob_sides == 1) & (recent_low <= ob_tops) & (recent_low >= ob_bots)
            if np.any(valid_mask):
                entry = float(m5_h[i - 2])
                sl = float(min(m5_l[i - 1], m5_l[i - 2])) - 0.00010
                risk_dist = entry - sl

                if sp.min_stop <= risk_dist <= sp.max_stop:
                    tp = entry + target_rr * risk_dist
                    c_end_m1 = m5_m1_end[i]
                    fill_m1 = None

                    for m in range(c_end_m1, min(len(b_m1_ts), c_end_m1 + 120)):
                        if b_m1_bid_l[m] <= sl:
                            break
                        if b_m1_ask_l[m] <= entry:
                            fill_m1 = m
                            break

                    if fill_m1 is not None:
                        fill_px = entry + sp.slip
                        exit_m1 = None
                        exit_px = None
                        reason = None

                        for m in range(fill_m1 + 1, min(len(b_m1_ts), fill_m1 + 720)):
                            if b_m1_bid_l[m] <= sl:
                                exit_m1 = m
                                exit_px = sl - sp.slip
                                reason = "SL"
                                break
                            if b_m1_bid_h[m] >= tp:
                                exit_m1 = m
                                exit_px = tp - sp.slip
                                reason = "TP"
                                break

                        if exit_m1 is None:
                            exit_m1 = min(len(b_m1_ts) - 1, fill_m1 + 720)
                            exit_px = b_m1_bid_c[exit_m1]
                            reason = "EOD"

                        net_pnl_pts = (exit_px - fill_px) - sp.commission_rt
                        net_r = net_pnl_pts / risk_dist

                        trades.append({
                            "day": cur_day, "symbol": symbol, "side": 1,
                            "entry": entry, "sl": sl, "tp": tp, "risk_dist": risk_dist,
                            "fill_i": fill_m1, "exit_i": exit_m1, "r": net_r, "reason": reason,
                        })
                        last_trade_day = cur_day

        # Bearish M5 FVG
        elif m5_h[i] < m5_l[i - 2] and (m5_l[i - 2] - m5_h[i]) >= min_fvg_m5:
            recent_high = max(m5_h[i], m5_h[i - 1], m5_h[i - 2])
            
            valid_mask = (ob_starts < cur_ts) & (ob_sides == -1) & (recent_high >= ob_bots) & (recent_high <= ob_tops)
            if np.any(valid_mask):
                entry = float(m5_l[i - 2])
                sl = float(max(m5_h[i - 1], m5_h[i - 2])) + 0.00010
                risk_dist = sl - entry

                if sp.min_stop <= risk_dist <= sp.max_stop:
                    tp = entry - target_rr * risk_dist
                    c_end_m1 = m5_m1_end[i]
                    fill_m1 = None

                    for m in range(c_end_m1, min(len(b_m1_ts), c_end_m1 + 120)):
                        if b_m1_ask_h[m] >= sl:
                            break
                        if b_m1_bid_h[m] >= entry:
                            fill_m1 = m
                            break

                    if fill_m1 is not None:
                        fill_px = entry - sp.slip
                        exit_m1 = None
                        exit_px = None
                        reason = None

                        for m in range(fill_m1 + 1, min(len(b_m1_ts), fill_m1 + 720)):
                            if b_m1_ask_h[m] >= sl:
                                exit_m1 = m
                                exit_px = sl + sp.slip
                                reason = "SL"
                                break
                            if b_m1_ask_l[m] <= tp:
                                exit_m1 = m
                                exit_px = tp + sp.slip
                                reason = "TP"
                                break

                        if exit_m1 is None:
                            exit_m1 = min(len(b_m1_ts) - 1, fill_m1 + 720)
                            exit_px = b_m1_ask_c[exit_m1]
                            reason = "EOD"

                        net_pnl_pts = (fill_px - exit_px) - sp.commission_rt
                        net_r = net_pnl_pts / risk_dist

                        trades.append({
                            "day": cur_day, "symbol": symbol, "side": -1,
                            "entry": entry, "sl": sl, "tp": tp, "risk_dist": risk_dist,
                            "fill_i": fill_m1, "exit_i": exit_m1, "r": net_r, "reason": reason,
                        })
                        last_trade_day = cur_day

    return pd.DataFrame(trades)
