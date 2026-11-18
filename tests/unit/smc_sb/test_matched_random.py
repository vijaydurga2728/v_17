"""Spec 3a matched control: determinism, matched features, eligibility, seed rule."""

from __future__ import annotations

import pandas as pd
import pytest

from v17.smc_sb.config import BASELINE, EXPERIMENT_OTE
from v17.smc_sb.engine import Engine
from v17.smc_sb.matched_random import (
    eligible_days,
    matched_control_test,
    seed_for,
    trade_features,
)


def _trades(synth):
    mk = synth.build(synth.scenario_m1())
    trades, _, _ = Engine(mk, BASELINE).run([synth.DAY])
    return mk, trades


def test_features_match_the_real_trade(synth):
    """Placement 10:30 (minute 30); placement price = ask close of the 10:29 bar = 102.5 + 0.1;
    offset = 102.6 - 101.6 = 1.0; stop distance 0.4; target distance 7.4."""
    _, trades = _trades(synth)
    f = trade_features(trades, BASELINE).iloc[0]
    assert (int(f.side), int(f.minute)) == (1, 30)
    assert f.offset == pytest.approx(1.0) and f.stop_d == pytest.approx(0.4)
    assert f.target_d == pytest.approx(7.4)


def test_control_is_deterministic_and_reports_fill_rate(synth):
    mk, trades = _trades(synth)
    days = [synth.DAY, pd.Timestamp("2024-03-15").date()]  # Friday has one 12:00 bar -> ineligible
    assert len(eligible_days(mk, days, BASELINE)) == 1
    a = matched_control_test(mk, trades, days, BASELINE, perms=20)
    b = matched_control_test(mk, trades, days, BASELINE, perms=20)
    assert a == b and a["perms"] == 20 and 0 < a["p_one_sided"] <= 1
    assert a["seed"] == 2026112100 and 0 < a["control_fill_rate"] <= 1
    # the only eligible day is the trade day itself, so every control replays the real trade exactly
    assert a["null_mean_r_median"] == pytest.approx(trades.r.iloc[0])
    assert a["p_one_sided"] == 1.0  # (1 + 20) / 21: null >= real in every permutation


def test_seed_rule():
    assert seed_for("SPX", BASELINE) == 2026112110
    assert seed_for("US30", EXPERIMENT_OTE) == 2026112121
