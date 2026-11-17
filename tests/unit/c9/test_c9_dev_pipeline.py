"""Phase 4 entrypoint tests on a fake bars root (no real market data).

Key guarantee: a normal development run never opens holdout partitions, even
when they exist on disk next to the dev data.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from v17.backtest import c9_dev_pipeline as pipe
from v17.backtest.c9_runner import load_m1, prepare
from v17.setups.c9_pdh_pdl import SYMBOL, Slot, full_rth_days


def _fake_month(year: int, month: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = full_rth_days(f"{year}-{month:02d}-01", f"{year}-{month:02d}-28")
    frames = []
    px = 4000.0
    for d in days:
        idx = pd.date_range(f"{d} 09:30", f"{d} 16:00", freq="1min", tz="America/New_York",
                            inclusive="left")
        mid = px + np.cumsum(rng.normal(0, 3, len(idx)))
        px = float(mid[-1])
        f = pd.DataFrame({"ts_utc": idx.tz_convert("UTC").asi8, "symbol": SYMBOL})
        for k, off in zip("ohlc", (0.0, 1.5, -1.5, 0.3), strict=True):
            f[f"bid_{k}"] = mid + off - 0.5
            f[f"ask_{k}"] = mid + off + 0.5
        f["bid_volume"] = 1.0
        f["ask_volume"] = 1.0
        f["spread_mid"] = 1.0
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    root = tmp_path / "bars"
    layout = [("dev", 2015, 1), ("dev", 2015, 2),          # cycle 9 dev
              ("dev", 2023, 1), ("holdout", 2025, 1)]       # cycle 9 HOLDOUT (poison)
    for i, (part, y, m) in enumerate(layout):
        d = root / SYMBOL / part / f"year={y}" / f"month={m:02d}"
        d.mkdir(parents=True)
        _fake_month(y, m, seed=i).to_parquet(d / "data.parquet", index=False)
    return root


@pytest.fixture
def read_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real = pq.read_table

    def spy(source, *a, **k):  # type: ignore[no-untyped-def]
        seen.append(str(source))
        return real(source, *a, **k)

    monkeypatch.setattr(pq, "read_table", spy)
    return seen


def test_dev_load_never_opens_holdout_partitions(fake_root: Path, read_spy: list[str]) -> None:
    m1 = load_m1("dev", root=fake_root)
    assert read_spy and all("year=2015" in p for p in read_spy)
    assert not any(f"year={y}" in p for p in read_spy for y in range(2023, 2027))
    assert m1.attrs["c9_load_audit"]["files_read"] == ["dev/year=2015/month=01",
                                                       "dev/year=2015/month=02"]


def test_run_dev_end_to_end_test_mode(fake_root: Path, read_spy: list[str], tmp_path: Path) -> None:
    out = tmp_path / "out"
    man = pipe.run_dev(out, bars_root=fake_root, n_perms=5)
    assert not any(f"year={y}" in p for p in read_spy for y in range(2023, 2027))
    for f in ("data_audit.json", "grid_report.csv", "slippage_sensitivity.csv",
              "mcpt_report.csv", "run_manifest.json"):
        assert (out / f).exists(), f
    assert len(list((out / "trades").glob("*.parquet"))) == 12
    audit = json.loads((out / "data_audit.json").read_text("utf-8"))
    assert audit["holdout_files_read"] == []
    assert audit["load"]["conflicting_timestamps"] == 0
    assert len(pd.read_csv(out / "grid_report.csv")) == 12
    rep = pd.read_csv(out / "mcpt_report.csv")
    assert len(rep) == 12 and rep["status"].notna().all()     # every slot reported
    assert man["official_gate_run"] is False
    assert man["verdict"].startswith("TEST RUN")


def test_official_flag_only_at_100k(fake_root: Path, tmp_path: Path) -> None:
    assert pipe.N_PERMS == 100_000
    man = pipe.run_dev(tmp_path / "o", bars_root=fake_root, n_perms=3)
    assert man["official_gate_run"] is False


def test_mcpt_stage_logs_perms_and_records_errors(fake_root: Path, tmp_path: Path) -> None:
    prep = prepare(load_m1("dev", root=fake_root), "dev")
    slot = Slot(0.0, "long_only", 1)
    rows = pipe.run_mcpt_stage(prep, [slot], tmp_path, n_perms=7)
    assert rows[0]["status"] == "ok" and rows[0]["n_perms"] == 7
    perms = pd.read_parquet(tmp_path / f"mcpt_perms_{slot.slot_id}.parquet")
    assert len(perms) == 7 and (perms["seed"] == 20261116000).all()
    assert rows[0]["p_value"] == pytest.approx((rows[0]["exceedances"] + 1) / 8)
    # A failing slot is reported with an error status, not skipped.
    tiny = prepare(load_m1("dev", root=fake_root, months=[(2015, 1)]), "dev")
    tiny.sess.offsets = tiny.sess.offsets[:3]   # 2 sessions -> bootstrap pool too small
    tiny.sess.dates = tiny.sess.dates[:2]
    bad = pipe.run_mcpt_stage(tiny, [slot], tmp_path, n_perms=3)
    assert bad[0]["status"].startswith("error: ValueError") and bad[0]["tier3_pass"] is False


def test_thresholds_are_frozen() -> None:
    assert pipe.TIER2_ALPHA == 0.05
    assert pytest.approx(0.0003787879, rel=1e-6) == pipe.TIER3_ALPHA
