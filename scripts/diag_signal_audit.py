"""Call setup.evaluate() directly on every in-window bar. Count exact drop reasons."""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from v17.backtest.precompute import precompute, snapshot_at
from v17.common.dtos import Signal
from v17.common.types import TF, Bias, Side, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider
from v17.setups.judas_swing import JudasSwing
from v17.setups.sessions import in_judas_window, in_silver_bullet_window
from v17.setups.silver_bullet import ZONE_TOLERANCE_PIPS, _PIP, SilverBullet, _pick_zone
from v17.setups.targets import passes_rr, pip_distance, rr

SYMBOL = Symbol(sys.argv[1] if len(sys.argv) > 1 else "EURUSD")
START = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=UTC) if len(sys.argv) > 2 else datetime(2024, 6, 1, tzinfo=UTC)
END = datetime.fromisoformat(sys.argv[3]).replace(tzinfo=UTC) if len(sys.argv) > 3 else datetime(2024, 6, 30, tzinfo=UTC)


def load_bars(symbol: Symbol, start: datetime, end: datetime) -> pd.DataFrame:
    s = get_settings()
    s.ensure_dirs()
    p = ParquetBarProvider(s.parquet_root)
    rows = [b.model_dump() for b in p.bars(symbol, TF.M1, start, end)]
    df = pd.DataFrame(rows)
    for col in ("open", "high", "low", "close", "spread_pips"):
        df[col] = df[col].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["volume"] = df["volume"].astype("int64")
    return df


def main() -> None:
    bars = load_bars(SYMBOL, START, END)
    pre = precompute(bars, SYMBOL)
    sb = SilverBullet()
    jd = JudasSwing()
    print(f"bars: {len(bars)}  tol: {ZONE_TOLERANCE_PIPS} pips")
    print(f"pre.zones_15m: {len(pre.zones_15m)}  pre.swings_4h: {len(pre.swings_4h)}  pre.sweeps_15m: {len(pre.sweeps_15m)}")

    sb_drops = {
        "bias_none": 0, "no_zone": 0, "pip_sl_fail": 0, "rr_fail": 0,
        "no_sweep": 0, "no_mss": 0, "signal": 0,
    }
    jd_drops = {"bias_none": 0, "asian_fail": 0, "no_zone": 0, "pip_sl_fail": 0, "rr_fail": 0, "signal": 0}
    sb_pip_sls: list[float] = []
    sb_rrs: list[float] = []

    for i, ts_val in enumerate(bars["ts"].iloc[:-1]):
        ts = ts_val.to_pydatetime()
        if not in_silver_bullet_window(ts) and not in_judas_window(ts):
            continue
        snap = snapshot_at(pre, ts)

        if in_silver_bullet_window(ts):
            if snap.bias == Bias.NONE:
                sb_drops["bias_none"] += 1
            else:
                side = Side.BUY if snap.bias == Bias.BULL else Side.SELL
                last_close = Decimal(str(float(bars["close"].iloc[i])))
                zone = _pick_zone(snap.zones, side, last_close, ts)
                if zone is None:
                    sb_drops["no_zone"] += 1
                else:
                    entry = (zone.top + zone.bottom) / 2
                    if side == Side.BUY:
                        sl = zone.bottom - Decimal("0.0001")
                        tp = entry + Decimal("22") * Decimal("0.0001")
                    else:
                        sl = zone.top + Decimal("0.0001")
                        tp = entry - Decimal("22") * Decimal("0.0001")
                    pip_sl = pip_distance(entry, sl)
                    sb_pip_sls.append(float(pip_sl))
                    if pip_sl < Decimal("2"):
                        sb_drops["pip_sl_fail"] += 1
                    else:
                        rr_val = rr(entry, sl, tp, side)
                        sb_rrs.append(float(rr_val))
                        if not passes_rr(rr_val):
                            sb_drops["rr_fail"] += 1
                        else:
                            from datetime import timedelta as _td
                            from v17.common.types import TF as _TF
                            from v17.setups.silver_bullet import (
                                MSS_LOOKBACK_MIN as _MSS,
                                SWEEP_LOOKBACK_MIN as _SW,
                            )
                            want_sweep = "ssl" if side == Side.BUY else "bsl"
                            sweep_ok = any(
                                s.kind == want_sweep
                                and (ts - s.at) <= _td(minutes=_SW)
                                for s in snap.sweeps
                            )
                            if not sweep_ok:
                                sb_drops["no_sweep"] += 1
                            else:
                                mss_ok = any(
                                    sw.kind == "mss"
                                    and sw.side == side
                                    and sw.tf == _TF.M1
                                    and (ts - sw.at) <= _td(minutes=_MSS)
                                    for sw in snap.swings
                                )
                                if not mss_ok:
                                    sb_drops["no_mss"] += 1
                                else:
                                    sb_drops["signal"] += 1

        if in_judas_window(ts):
            sig = jd.evaluate(snap, ts, bars.iloc[: i + 1])
            if sig is None:
                # breakdown
                if snap.bias == Bias.NONE:
                    jd_drops["bias_none"] += 1
                else:
                    try:
                        from v17.setups.sessions import asian_high_low
                        _ = asian_high_low(bars.iloc[: i + 1], ts)
                        jd_drops["no_zone"] += 1  # most likely culprit
                    except Exception:
                        jd_drops["asian_fail"] += 1
            else:
                jd_drops["signal"] += 1

    print("\nSB drops:")
    for k, v in sb_drops.items():
        print(f"  {k}: {v}")
    print("\nJudas drops:")
    for k, v in jd_drops.items():
        print(f"  {k}: {v}")
    if sb_pip_sls:
        s = sorted(sb_pip_sls)
        print(f"\nSB pip_sl distribution: min={s[0]:.1f} p25={s[len(s)//4]:.1f} med={s[len(s)//2]:.1f} p75={s[3*len(s)//4]:.1f} max={s[-1]:.1f}")
        print(f"  fraction with pip_sl < 5: {sum(1 for x in sb_pip_sls if x < 5) / len(sb_pip_sls):.1%}")
    if sb_rrs:
        r = sorted(sb_rrs)
        print(f"SB rr distribution: min={r[0]:.2f} p25={r[len(r)//4]:.2f} med={r[len(r)//2]:.2f} p75={r[3*len(r)//4]:.2f} max={r[-1]:.2f}")
        print(f"  fraction rr < 1.5: {sum(1 for x in sb_rrs if x < 1.5) / len(sb_rrs):.1%}")


if __name__ == "__main__":
    main()
