import numpy as np
import pandas as pd
from v17.validation.secondary_gates import evaluate_secondary


def test_fails_g2_when_trade_count_under_50():
    agg = pd.DataFrame({
        "pnl_r": [1.0] * 30,
        "fold_id": [1] * 30,
        "ts_entry_ns": [i * 1_000_000_000 for i in range(30)],
    })
    report = evaluate_secondary(agg, cost_stress_pf=2.0)
    assert report.G2_pass is False


def test_fails_g3_when_a_fold_is_net_negative():
    data = {"pnl_r": [], "fold_id": [], "ts_entry_ns": []}
    for f in range(1, 8):
        for _ in range(10):
            data["pnl_r"].append(1.0 if f != 3 else -1.0)
            data["fold_id"].append(f)
            data["ts_entry_ns"].append(len(data["ts_entry_ns"]) * 1_000_000_000)
    agg = pd.DataFrame(data)
    report = evaluate_secondary(agg, cost_stress_pf=2.0)
    assert report.G3_pass is False


def test_passes_all_gates_on_strong_series():
    pnls = np.concatenate([
        np.full(10, 1.0) if f % 2 == 0 else np.full(10, 0.5)
        for f in range(1, 8)
    ])
    agg = pd.DataFrame({
        "pnl_r": pnls,
        "fold_id": np.repeat(range(1, 8), 10),
        "ts_entry_ns": np.arange(70) * 1_000_000_000,
    })
    report = evaluate_secondary(agg, cost_stress_pf=1.5)
    assert report.all_pass


def test_fails_g5_when_cost_stress_pf_below_11():
    pnls = np.full(70, 1.0)
    agg = pd.DataFrame({
        "pnl_r": pnls,
        "fold_id": np.repeat(range(1, 8), 10),
        "ts_entry_ns": np.arange(70) * 1_000_000_000,
    })
    report = evaluate_secondary(agg, cost_stress_pf=1.05)
    assert report.G5_pass is False
    assert report.all_pass is False
