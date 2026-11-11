"""Cycle 4B sealed-holdout — RSI2-USATECHIDXUSD only.

GATE-LIMITED ADVANCE per docs/superpowers/specs/2026-11-11-cycle4b-mcpt-scheme-addendum.md.

Window: 2025-01-01 → 2026-10-18.
Rules locked verbatim from C4B-S5 commit 1465ef3. No parameter changes.

Pass = HOLDOUT-PASS PRE-LIVE (not DEPLOY — scheme-1 MCPT still required).
Criteria (ALL must hold):
  PF >= 1.3
  WR >= 50%
  max_dd (R-units cumulative) < 10
  no FTMO hard-freeze under ORBRiskEngine(10_000)
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.rsi2_runner import run_rsi2_oos_batch
from v17.backtest.walkforward import Fold
from v17.data.parquet_store import read_bars_d1
from v17.risk.orb_risk_engine import ORBRiskEngine
from v17.setups.rsi2_engines import RSI2_CATALOG
from v17.validation.stats import compute_stats


R_CASH_PER_TRADE = 50.0   # 0.5% of $10k = $50 at 1R
STARTING_EQUITY = 10_000.0


def main() -> None:
    engine = RSI2_CATALOG[0]
    assert engine.symbol == "USATECHIDXUSD", f"expected NAS100; got {engine.symbol}"

    bars = read_bars_d1(engine.symbol, "holdout", root=None)
    if bars.empty:
        raise SystemExit("[c4b-ho] no holdout bars found")
    print(f"[c4b-ho] holdout bars: {len(bars):,}", flush=True)

    oos_start = pd.Timestamp("2025-01-01", tz="UTC").value
    oos_end = pd.Timestamp("2026-10-19", tz="UTC").value  # inclusive upper
    fold = Fold(
        fold_id=100,
        train_start=0,
        train_end=oos_start - 1,
        oos_start=oos_start,
        oos_end=oos_end,
    )

    logs = run_rsi2_oos_batch(engine, bars, [fold])
    trades = [t for l in logs for t in l.trades]
    trades.sort(key=lambda t: t["ts_entry_ns"])
    print(f"[c4b-ho] trades: {len(trades)}", flush=True)

    if not trades:
        print("[c4b-ho] ZERO TRADES — holdout FAILS by default")
        verdict = {
            "engine_id": engine.engine_id, "trades": 0, "verdict": "SHELVE",
            "reason": "no trades on holdout",
        }
        (Path("docs/superpowers/plans") / "c4b_holdout_report_2026-11-11.md").write_text(
            "# C4B Holdout Report — ZERO TRADES\n\nSHELVE.\n", encoding="utf-8"
        )
        return

    # FTMO circuit-breaker walk.
    risk = ORBRiskEngine(STARTING_EQUITY)
    allowed_trades: list[dict] = []
    rejected_count = 0
    current_day_ns = None
    for t in trades:
        day_ns = (t["ts_entry_ns"] // 86_400_000_000_000) * 86_400_000_000_000
        if current_day_ns is None or day_ns != current_day_ns:
            risk.start_of_day(day_ns)
            current_day_ns = day_ns
        if not risk.allow_trade():
            rejected_count += 1
            continue
        pnl_cash = float(t["pnl_r"]) * R_CASH_PER_TRADE
        risk.on_trade_close(pnl_cash, t["ts_exit_ns"])
        t_copy = dict(t)
        t_copy["pnl_cash"] = pnl_cash
        allowed_trades.append(t_copy)

    hard_frozen = not risk.allow_trade() and risk._permanently_frozen  # type: ignore[attr-defined]

    # Stats on allowed trades.
    if allowed_trades:
        pnl_r = np.array([t["pnl_r"] for t in allowed_trades])
        ts = np.array([t["ts_entry_ns"] for t in allowed_trades])
        s = compute_stats(pnl_r, ts)
        pf = float(s.pf) if np.isfinite(s.pf) else 0.0
        wr = float(s.win_rate)
        # Max-DD in R-units from cumulative pnl_r curve.
        cum = np.cumsum(pnl_r)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        max_dd_r = float(dd.max()) if len(dd) > 0 else 0.0
    else:
        pf, wr, max_dd_r = 0.0, 0.0, 0.0

    passes = {
        "pf_ge_1_3": pf >= 1.3,
        "wr_ge_0_5": wr >= 0.5,
        "max_dd_lt_10R": max_dd_r < 10.0,
        "no_hard_freeze": not hard_frozen,
    }
    all_pass = all(passes.values())
    verdict = "HOLDOUT-PASS PRE-LIVE" if all_pass else "SHELVE"

    print(f"[c4b-ho] PF={pf:.3f} WR={wr:.3f} max_dd_R={max_dd_r:.2f} hard_frozen={hard_frozen}", flush=True)
    print(f"[c4b-ho] verdict: {verdict}", flush=True)

    # Report
    md = [
        "# RSI2-USATECHIDXUSD Sealed-Holdout Report — 2026-11-11",
        "",
        "**Window:** 2025-01-01 -> 2026-10-18 (D1 bars).",
        "**Rules:** locked verbatim from C4B-S5 commit `1465ef3`. No param changes.",
        "**Status:** GATE-LIMITED ADVANCE per `2026-11-11-cycle4b-mcpt-scheme-addendum.md`.",
        "",
        "## Results",
        "",
        f"- Trades submitted: **{len(trades)}**",
        f"- Trades executed (post-breaker): **{len(allowed_trades)}**",
        f"- Trades rejected by breaker: **{rejected_count}**",
        f"- PF: **{pf:.3f}** (require >= 1.3: {'PASS' if passes['pf_ge_1_3'] else 'FAIL'})",
        f"- Win rate: **{wr:.1%}** (require >= 50%: {'PASS' if passes['wr_ge_0_5'] else 'FAIL'})",
        f"- Max DD (R-cumulative): **{max_dd_r:.2f}** (require < 10R: {'PASS' if passes['max_dd_lt_10R'] else 'FAIL'})",
        f"- Hard-freeze triggered: **{hard_frozen}** (require False: {'PASS' if passes['no_hard_freeze'] else 'FAIL'})",
        "",
        f"## Verdict: {verdict}",
        "",
        "## Caveats (binding)",
        "",
        "- Even a HOLDOUT-PASS result is **NOT DEPLOY**. Live money is barred until:",
        "  1. Scheme-1 MCPT is built (signal-time permutation with engine re-run).",
        "  2. RSI2-NAS100 passes scheme-1 MCPT at p_pf < 0.05 single-pair (no Bonferroni).",
        "  3. 90-day free demo follows per `user_trading_goals.md`.",
        "- Compound end-to-end prior (holdout pass + scheme-1 pass + demo + FTMO + payout): 5-10%.",
    ]
    out = Path("docs/superpowers/plans/c4b_holdout_report_2026-11-11.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"[c4b-ho] wrote {out}", flush=True)

    # JSON for machine consumption.
    out_json = Path("out/c4b_gates/holdout_summary.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({
        "engine_id": engine.engine_id,
        "trades_submitted": len(trades),
        "trades_executed": len(allowed_trades),
        "trades_rejected": rejected_count,
        "pf": pf, "win_rate": wr, "max_dd_r": max_dd_r,
        "hard_frozen": hard_frozen,
        "passes": passes, "verdict": verdict,
    }, indent=2))


if __name__ == "__main__":
    main()
