from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from v17.common.types import TF, Symbol
from v17.data.providers import ParquetBarProvider
from v17.structure.engine import DefaultStructureEngine


@pytest.mark.integration
def test_structure_on_real_eurusd_london_session() -> None:
    pq = Path("data/parquet")
    if not (pq / "EURUSD").exists():
        pytest.skip("real data not ingested")
    p = ParquetBarProvider(pq)

    def _df(tf: TF, start: datetime, end: datetime) -> pd.DataFrame:
        bars = list(p.bars(Symbol("EURUSD"), tf, start, end))
        rows = [b.model_dump() for b in bars]
        df = pd.DataFrame(rows)
        if not df.empty:
            for col in ("open", "high", "low", "close", "spread_pips"):
                df[col] = df[col].astype(float)
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df

    bars_by_tf = {
        TF.D1: _df(TF.D1, datetime(2024, 3, 1, tzinfo=UTC), datetime(2024, 6, 3, 23, tzinfo=UTC)),
        TF.H4: _df(TF.H4, datetime(2024, 5, 1, tzinfo=UTC), datetime(2024, 6, 3, 23, tzinfo=UTC)),
        TF.M15: _df(TF.M15, datetime(2024, 6, 1, tzinfo=UTC), datetime(2024, 6, 3, 23, tzinfo=UTC)),
        TF.M1: _df(TF.M1, datetime(2024, 6, 3, 6, tzinfo=UTC), datetime(2024, 6, 3, 9, tzinfo=UTC)),
    }
    for tf, df in bars_by_tf.items():
        assert not df.empty, f"empty frame for {tf}"

    eng = DefaultStructureEngine(symbol=Symbol("EURUSD"))
    snap = eng.analyze(bars_by_tf)
    assert snap.symbol == Symbol("EURUSD")
    assert snap.bias.value in {"bull", "bear", "none"}
    print(
        f"bias={snap.bias.value} zones={len(snap.zones)} "
        f"swings={len(snap.swings)} sweeps={len(snap.sweeps)}"
    )
