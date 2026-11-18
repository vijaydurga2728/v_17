"""End-to-end synthetic day with hand-computed expectations (conftest scenario)."""

from __future__ import annotations

import dataclasses

import pytest

from v17.smc_sb.config import BASELINE, EXPERIMENT_OTE, EXPERIMENT_SMT
from v17.smc_sb.engine import Engine


def test_scenario_trade_matches_hand_calculation(synth):
    """Bias: pivot highs 110 -> 115 (HH), pivot lows 89 -> 91 (HL) => bullish; EQ = (115 + 91) / 2 = 103.
    PDH/PDL = 109/99. Sweep 10:00 5m low 98.5 < 99, close 99.4 > 99. 15m swing high 102.0 (09:30 candle)
    confirmed by 09:45 and 10:00; 10:15 candle closes 102.5 > 102.0 => MSS at 10:30. FVG c1 10:15 high 101.2,
    c3 10:25 low 101.6 (formed 10:30 = MSS close). Entry 101.6 < 103, stop 101.2, 1R = 0.4 + 0.5 = 0.9.
    Target PDH 109 (untouched, 7.4 >= 1.8). Fill 10:32 (ask 101.45 <= 101.6; bid low 101.25 > stop). Target 10:47 (bid 109.4)."""
    mk = synth.build(synth.scenario_m1())
    res = Engine(mk, BASELINE).run_day(synth.DAY)
    assert res.reason == "trade", res.events[-1]
    t = res.trade
    assert t["side"] == 1 and t["htf_bias"] == "HH+HL" and t["equilibrium"] == 103.0
    assert (
        t["liquidity_ref"] == "PDL"
        and t["liquidity_ref_price"] == 99.0
        and t["sweep_price"] == 98.5
    )
    assert t["sweep_ts"].startswith("2024-03-18T10:00")
    assert t["mss_ts"].startswith("2024-03-18T10:30") and t["mss_broken_swing"] == 102.0
    assert t["displacement_candle_ts"].startswith("2024-03-18T10:20")
    assert (t["fvg_bottom"], t["fvg_top"]) == (101.2, 101.6)
    assert (t["limit"], t["stop"], t["target"], t["target_name"]) == (101.6, 101.2, 109.0, "PDH")
    assert t["r_unit"] == pytest.approx(0.9)
    assert t["fill_ts"].startswith("2024-03-18T10:32") and t["exit_ts"].startswith(
        "2024-03-18T10:47"
    )
    assert t["exit_reason"] == "target" and t["r"] == pytest.approx(7.4 / 0.9)
    assert t["pd_state"] == "discount" and t["smt_status"] == "disabled"
    stages = [e["stage"] for e in res.events]
    assert stages == [
        "bias",
        "levels",
        "asia_missing",
        "sweep",
        "mss",
        "fvg",
        "premium_discount",
        "targets",
        "order_created",
        "order_filled",
        "exit",
    ]


def test_model_b_rejects_when_proximal_outside_ote(synth):
    """Anchors L = 98.5, H = 102.6 => zone [102.6 - 0.79*4.1, 102.6 - 0.62*4.1] = [99.361, 100.058]; 101.6 outside."""
    mk = synth.build(synth.scenario_m1())
    res = Engine(mk, EXPERIMENT_OTE).run_day(synth.DAY)
    assert res.reason == "ote_proximal_outside_zone"
    ote = next(e for e in res.events if e["stage"] == "ote")
    assert ote["zone_lo"] == pytest.approx(99.361) and ote["zone_hi"] == pytest.approx(100.058)


def test_missing_m1_bar_rejects_day_without_substitution(synth):
    df = synth.scenario_m1()
    ts = df.ts_utc.to_numpy()
    import pandas as pd

    drop = pd.Timestamp("2024-03-18 10:40", tz="America/New_York").value
    mk = synth.build(df[ts != drop])
    res = Engine(mk, BASELINE).run_day(synth.DAY)
    assert res.reason == "missing_m1"


def test_doubled_costs_change_execution_not_signals(synth):
    """Spread 0.4 + slippage 1.0: fill bar ask 101.55 <= 101.6 fills, but bid low 101.15 <= stop 101.2 on the fill
    bar => stop first. 1R = 0.4 + 1.0 = 1.4; exit 101.2 - 1.0 = 100.2 => R = -1.0. Signals are unchanged."""
    from v17.smc_sb.data import widen_costs

    mk = synth.build(widen_costs(synth.scenario_m1(), 2.0))
    cfg = dataclasses.replace(BASELINE, cost_multiplier=2.0)
    res = Engine(mk, cfg).run_day(synth.DAY)
    assert res.reason == "trade"
    t = res.trade
    assert (t["limit"], t["stop"], t["target"]) == (101.6, 101.2, 109.0)
    assert (
        t["r_unit"] == pytest.approx(1.4)
        and t["exit_reason"] == "stop"
        and t["r"] == pytest.approx(-1.0)
    )
    assert t["fill_ts"] == t["exit_ts"]


def test_engine_is_deterministic(synth):
    mk = synth.build(synth.scenario_m1())
    a = Engine(mk, BASELINE).run_day(synth.DAY)
    b = Engine(mk, BASELINE).run_day(synth.DAY)
    assert repr(a.trade) == repr(b.trade) and repr(a.events) == repr(b.events)


def test_smt_experiment_requires_partner(synth):
    mk = synth.build(synth.scenario_m1())
    with pytest.raises(ValueError, match="partner"):
        Engine(mk, EXPERIMENT_SMT)


def _partner(synth, low_1000: float):
    """Same scenario shifted +5 (PDL 104), with the 10:00 candle low set to `low_1000`."""
    import pandas as pd

    import v17.smc_sb.data as d

    cands = [(c[0], c[1] + 5, c[2] + 5, c[3] + 5, c[4] + 5) for c in synth.CANDLES_5M]
    cands[18] = ("10:00", 104.5, 104.6, low_1000, 104.4)
    df = synth.scenario_m1(candles=cands, tail=114.2)
    prior = df.ts_utc < pd.Timestamp("2024-03-18", tz="America/New_York").value
    for col in [c for c in df.columns if c != "ts_utc"]:
        df.loc[prior, col] += 5
    return d.build_market("SPX", df)


def test_smt_divergence_when_partner_holds_its_pdl(synth):
    mk = synth.build(synth.scenario_m1())
    res = Engine(mk, EXPERIMENT_SMT, _partner(synth, 104.1)).run_day(synth.DAY)
    assert res.reason == "trade" and res.trade["smt_status"] == "smt_divergence"


def test_smt_rejects_when_partner_also_sweeps(synth):
    mk = synth.build(synth.scenario_m1())
    res = Engine(mk, EXPERIMENT_SMT, _partner(synth, 103.5)).run_day(synth.DAY)
    assert res.reason == "smt_no_divergence"
