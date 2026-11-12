import pandas as pd

from v17.validation.c6_gates import compute_metrics, evaluate_dev_gates, evaluate_holdout_gates


def _mk_trades(pnls):
    return pd.DataFrame({
        "entry_ts_ns": [pd.Timestamp(f"2020-01-{i+1:02d}", tz='UTC').value for i in range(len(pnls))],
        "net_pnl_usd": pnls,
        "equity_sod": [10_000.0] * len(pnls),
        "r_multiple": [p / 50.0 for p in pnls],
    })


def _mk_eq(points):
    return pd.DataFrame({"ts_utc": [i * 86_400_000_000_000 for i in range(len(points))], "equity": points})


def test_metrics_basic():
    trades = _mk_trades([50, -25, 100, -40, 60])
    eq = _mk_eq([10_000, 10_050, 10_025, 10_125, 10_085, 10_145])
    m = compute_metrics(trades, eq)
    assert m["trade_count"] == 5
    assert m["pf"] > 1.0


def test_dev_gates_pass_mock_strong():
    m = {"sharpe": 1.5, "pf": 1.5, "trade_count": 900, "max_daily_loss_pct": -0.02,
         "max_consec_losing_days": 3, "worst_month_return": -0.01}
    g = evaluate_dev_gates(m, mcpt_p=0.02, paired_a=0.01, paired_b=0.08, paired_c=0.09)
    assert g["all_pass"] is True


def test_dev_gates_fail_low_sharpe():
    m = {"sharpe": 0.8, "pf": 1.5, "trade_count": 900, "max_daily_loss_pct": -0.02,
         "max_consec_losing_days": 3, "worst_month_return": -0.01}
    g = evaluate_dev_gates(m, mcpt_p=0.02, paired_a=0.01, paired_b=0.08, paired_c=0.09)
    assert g["D1"] is False
    assert g["all_pass"] is False


def test_holdout_gates():
    m = {"sharpe": 0.9, "pf": 1.2, "trade_count": 200, "max_daily_loss_pct": -0.02,
         "max_consec_losing_days": 3, "worst_month_return": -0.03}
    g = evaluate_holdout_gates(m, dev_sharpe=1.2, mcpt_p=0.08)
    # 0.9 >= 0.7 * 1.2 = 0.84 -> H1 pass. PF 1.2 < 1.15? 1.2 > 1.15 so pass.
    assert g["H1"] is True
    assert g["H2"] is True
    assert g["H3"] is True
    assert g["H4"] is True
    assert g["H5"] is True
    assert g["all_pass"] is True
