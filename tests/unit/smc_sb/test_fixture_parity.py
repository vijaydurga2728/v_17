"""Review round 3 section 3: every targeted fixture must match between the main engine and the independent
reference AND satisfy its required assertion (see scripts/c21_fixtures.py)."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from c21_fixture_parity import XNYS, check  # noqa: E402
from c21_fixtures import DAY, fixtures  # noqa: E402

from v17.smc_sb.config import BASELINE  # noqa: E402
from v17.smc_sb.data import build_market  # noqa: E402
from v17.smc_sb.engine import Engine  # noqa: E402

FIXTURES = fixtures()


@pytest.mark.parametrize("fx", FIXTURES, ids=[f.name for f in FIXTURES])
def test_fixture_parity_and_assertion(fx):
    ok, detail = check(fx)
    assert ok, detail


def test_rescan_fixture_event_trail():
    fx = next(f for f in FIXTURES if f.name == "one_pending_then_rescan")
    mk = build_market("NAS100", fx.m1, xnys=XNYS, early_close=fx.early)
    res = Engine(mk, dataclasses.replace(BASELINE, order_expiry=fx.expiry)).run_day(DAY)
    trail = [
        (e["stage"], e.get("ref", ""))
        for e in res.events
        if e["stage"] in ("sweep", "order_created", "order_expired_cancelled", "rescan_ended")
    ]
    assert trail == [
        ("sweep", "ASIA_LOW"),
        ("order_created", ""),
        ("order_expired_cancelled", ""),
        ("sweep", "PDL"),
        ("rescan_ended", ""),
    ]
