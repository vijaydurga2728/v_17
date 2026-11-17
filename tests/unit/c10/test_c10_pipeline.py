"""Cycle 10 dev pipeline on a fake bars root: never opens holdout partitions."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from v17.backtest import c10_dev_pipeline as pipe
from v17.setups.c9_pdh_pdl import SYMBOL, full_rth_days


def _fake_month(year: int, month: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames, px = [], 4000.0
    for d in full_rth_days(f"{year}-{month:02d}-01", f"{year}-{month:02d}-28"):
        idx = pd.date_range(f"{d} 09:00", f"{d} 16:30", freq="1min", tz="America/New_York",
                            inclusive="left")
        mid = px + np.cumsum(rng.normal(0, 3, len(idx)))
        px = float(mid[-1])
        f = pd.DataFrame({"ts_utc": idx.tz_convert("UTC").asi8, "symbol": SYMBOL})
        for k, off in zip("ohlc", (0.0, 1.5, -1.5, 0.3), strict=True):
            f[f"bid_{k}"] = mid + off - 0.5
            f[f"ask_{k}"] = mid + off + 0.5
        f["bid_volume"] = rng.random(len(idx))
        f["ask_volume"] = rng.random(len(idx))
        f["spread_mid"] = 1.0
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    root = tmp_path / "bars"
    for i, (part, y, m) in enumerate([("dev", 2015, 1), ("dev", 2015, 2), ("dev", 2015, 3),
                                      ("dev", 2023, 1), ("holdout", 2025, 1)]):
        d = root / SYMBOL / part / f"year={y}" / f"month={m:02d}"
        d.mkdir(parents=True)
        _fake_month(y, m, i).to_parquet(d / "data.parquet", index=False)
    return root


def test_dev_run_outputs_and_no_holdout_reads(fake_root: Path, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real = pq.read_table

    def spy(source, *a, **k):  # type: ignore[no-untyped-def]
        seen.append(str(source))
        return real(source, *a, **k)

    monkeypatch.setattr(pq, "read_table", spy)
    out = tmp_path / "out"
    man = pipe.run_dev(out, bars_root=fake_root, n_perms=5)
    assert seen and not any(f"year={y}" in p for p in seen for y in range(2023, 2027))
    for f in ("data_audit.json", "grid_report.csv", "slippage_sensitivity.csv",
              "mcpt_report.csv", "run_manifest.json"):
        assert (out / f).exists(), f
    assert sorted(p.name for p in (out / "trades").glob("*.parquet")) == [
        "B.parquet", "G.parquet", "Z.parquet"]
    audit = json.loads((out / "data_audit.json").read_text("utf-8"))
    assert audit["holdout_files_read"] == [] and audit["days_without_r_unit"] == 14
    rep = pd.read_csv(out / "mcpt_report.csv")
    assert list(rep["slot"]) == ["G", "B", "Z"] and rep["status"].notna().all()
    assert man["official_gate_run"] is False and man["verdict"].startswith("TEST RUN")


def test_frozen_thresholds() -> None:
    assert pipe.N_PERMS == 100_000
    assert pytest.approx(0.000370370, rel=1e-5) == pipe.TIER3_ALPHA
