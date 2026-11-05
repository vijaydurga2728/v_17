from pathlib import Path
import pandas as pd
import numpy as np
from v17.validation.mcpt_runner import run_mcpt


def test_mcpt_runner_produces_permutations_and_pvalues(tmp_path):
    rng = np.random.default_rng(1)
    trades = pd.DataFrame({
        "ts_entry_ns": pd.date_range("2018-01-01 10:00", periods=20, freq="7D", tz="UTC").astype("int64"),
        "pnl_r": rng.normal(0, 1, 20),
        "symbol": "EURUSD",
        "side": "LONG",
    })
    bars = pd.DataFrame({
        "ts_utc": pd.date_range("2018-01-01 09:00", "2018-07-01", freq="min", tz="UTC").astype("int64"),
        "symbol": "EURUSD",
    })
    res = run_mcpt(
        engine_id="SB-NYAM-CE", trades=trades, bars=bars, calendar=pd.DataFrame(),
        scheme="pnl_bootstrap", n_permutations=100, out_root=tmp_path,
    )
    perm_file = tmp_path / "mcpt" / "SB-NYAM-CE" / "pnl_bootstrap" / "permutations.parquet"
    assert perm_file.exists()
    assert "p_sharpe" in res
    assert "p_pf" in res
    assert res["n_permutations"] == 100


def test_mcpt_runner_signal_time_scheme_deferred(tmp_path):
    """Scheme 1 deferred per spec section 7 amendment (2026-11-04, Audit 3)."""
    import pytest
    trades = pd.DataFrame({
        "ts_entry_ns": pd.date_range("2018-01-01 10:00", periods=10, freq="D", tz="UTC").astype("int64"),
        "pnl_r": [1.0, -0.5] * 5,
        "symbol": "EURUSD",
        "side": "LONG",
    })
    bars = pd.DataFrame({
        "ts_utc": pd.date_range("2018-01-01 09:00", "2018-07-01", freq="min", tz="UTC").astype("int64"),
        "symbol": "EURUSD",
    })
    with pytest.raises(NotImplementedError, match="DEFERRED"):
        run_mcpt(
            engine_id="SB-LDN-CE", trades=trades, bars=bars, calendar=pd.DataFrame(),
            scheme="signal_time", n_permutations=20, out_root=tmp_path,
        )
