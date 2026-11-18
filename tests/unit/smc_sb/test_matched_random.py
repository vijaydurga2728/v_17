"""R24 matched random-entry null: determinism and day eligibility."""

from __future__ import annotations

import pandas as pd

from v17.smc_sb.config import BASELINE
from v17.smc_sb.engine import Engine
from v17.smc_sb.matched_random import eligible_days, matched_random_test


def test_null_is_deterministic_and_excludes_incomplete_days(synth):
    mk = synth.build(synth.scenario_m1())
    trades, _, _ = Engine(mk, BASELINE).run([synth.DAY])
    assert len(trades) == 1
    days = [
        synth.DAY,
        pd.Timestamp("2024-03-15").date(),
    ]  # Friday has a single 12:00 bar -> ineligible
    assert len(eligible_days(mk, days, BASELINE)) == 1
    a = matched_random_test(mk, trades, days, BASELINE, seed=7, perms=50)
    b = matched_random_test(mk, trades, days, BASELINE, seed=7, perms=50)
    assert a == b and a["perms"] == 50 and 0 < a["p_mean_r"] <= 1
