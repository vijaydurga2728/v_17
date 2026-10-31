from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from v17.common.dtos import StructureSnapshot
from v17.common.types import TF, Symbol
from v17.data.providers import ParquetBarProvider
from v17.setups.judas_swing import JudasSwing
from v17.setups.silver_bullet import SilverBullet
from v17.structure.engine import DefaultStructureEngine


def _df(p: ParquetBarProvider, sym: Symbol, tf: TF, start: datetime, end: datetime) -> pd.DataFrame:
    bars = list(p.bars(sym, tf, start, end))
    rows = [b.model_dump() for b in bars]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("open", "high", "low", "close", "spread_pips"):
        df[col] = df[col].astype(float)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


@pytest.mark.integration
def test_setups_on_real_eurusd_london_killzone() -> None:
    pq = Path("data/parquet")
    if not (pq / "EURUSD").exists():
        pytest.skip("real data not ingested")
    p = ParquetBarProvider(pq)
    sym = Symbol("EURUSD")

    # June 5, 2024 (Wed) — valid trading day
    day = datetime(2024, 6, 5, tzinfo=UTC)
    bars_by_tf = {
        TF.D1: _df(p, sym, TF.D1, day - timedelta(days=90), day + timedelta(hours=23)),
        TF.H4: _df(p, sym, TF.H4, day - timedelta(days=30), day + timedelta(hours=23)),
        TF.M15: _df(p, sym, TF.M15, day - timedelta(days=5), day + timedelta(hours=23)),
        TF.M1: _df(p, sym, TF.M1, day - timedelta(hours=12), day + timedelta(hours=12)),
    }
    for tf, df in bars_by_tf.items():
        assert not df.empty, f"empty frame for {tf}"

    snap: StructureSnapshot = DefaultStructureEngine(symbol=sym).analyze(bars_by_tf)

    sb = SilverBullet()
    judas = JudasSwing()
    bars_1m = bars_by_tf[TF.M1]
    sb_count = 0
    judas_count = 0
    first_sb_sig = None
    first_judas_sig = None
    # Iterate 1m bars inside killzone (06:00 UTC - 10:00 UTC covers London killzone)
    killzone = bars_1m[
        (bars_1m["ts"] >= pd.Timestamp(day + timedelta(hours=6)))
        & (bars_1m["ts"] <= pd.Timestamp(day + timedelta(hours=10)))
    ]
    for _, bar in killzone.iterrows():
        now = bar["ts"].to_pydatetime()
        sub = bars_1m[bars_1m["ts"] <= bar["ts"]]
        s1 = sb.evaluate(snap, now, sub)
        if s1 is not None:
            sb_count += 1
            if first_sb_sig is None:
                first_sb_sig = s1
        s2 = judas.evaluate(snap, now, sub)
        if s2 is not None:
            judas_count += 1
            if first_judas_sig is None:
                first_judas_sig = s2

    print(f"sb_signals={sb_count} judas_signals={judas_count}")
    if first_sb_sig is not None:
        print(f"first_sb={first_sb_sig.model_dump_json()}")
    if first_judas_sig is not None:
        print(f"first_judas={first_judas_sig.model_dump_json()}")
