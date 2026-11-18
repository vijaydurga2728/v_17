"""Cycle 21 differential check: main engine vs independent reference, on deterministic SYNTHETIC markets only
(no real market data, so no strategy execution on 2018-2024 and no holdout access).

Compares every weekday's outcome (trade or exact rejection reason) and every trade's fields for variants A
(baseline), B (OTE) and SMT. Writes out/c21/reference_check.md and out/c21/hand_check.md.
"""

# ruff: noqa: E402
from __future__ import annotations

import datetime as dt
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from c21_reference_impl import RefMarket, run_day
from c21_synthetic import generate

from v17.smc_sb.config import BASELINE, EXPERIMENT_OTE, EXPERIMENT_SMT
from v17.smc_sb.data import build_market
from v17.smc_sb.engine import Engine

OUT = REPO / "out" / "c21"
SEEDS = [7, 11, 23, 42, 101, 202]
SPANS = {
    7: ("2019-01-01", "2020-12-31"),
    11: ("2021-01-01", "2022-12-31"),
    23: ("2023-01-01", "2024-12-31"),
    42: ("2019-01-01", "2020-12-31"),
    101: ("2021-01-01", "2022-12-31"),
    202: ("2023-01-01", "2024-12-31"),
}
NY = "America/New_York"
FIELDS = [
    "side",
    "ref",
    "sweep_ns",
    "mss_ns",
    "swing",
    "fvg_bottom",
    "fvg_top",
    "limit",
    "stop",
    "target_name",
    "target",
    "fill_ns",
    "exit_ns",
    "exit_reason",
    "exit_price",
    "gap_through",
    "data_gap",
    "smt",
]


def ns_of(iso: str) -> int:
    return pd.Timestamp(iso).value


def main_view(t: dict) -> dict:
    return {
        "side": t["side"],
        "ref": t["liquidity_ref"],
        "sweep_ns": ns_of(t["sweep_ts"]),
        "mss_ns": ns_of(t["mss_ts"]),
        "swing": t["mss_broken_swing"],
        "fvg_bottom": t["fvg_bottom"],
        "fvg_top": t["fvg_top"],
        "limit": t["limit"],
        "stop": t["stop"],
        "target_name": t["target_name"],
        "target": t["target"],
        "fill_ns": ns_of(t["fill_ts"]),
        "exit_ns": ns_of(t["exit_ts"]),
        "exit_reason": t["exit_reason"],
        "exit_price": t["exit_price"],
        "gap_through": bool(t["gap_through"]),
        "data_gap": bool(t["data_gap"]),
        "smt": t["smt_status"],
        "r": t["r"],
    }


def same(a: object, b: object) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def run() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Cycle 21 independent re-implementation check (synthetic markets only)",
        "",
        "Main engine `src/v17/smc_sb` vs `scripts/c21_reference_impl.py` (no shared strategy code).",
        "Each row compares every weekday after a 1-month warm-up: day outcome (trade or exact rejection reason)",
        "and, for trades, all fields below plus R (tolerance 1e-9).",
        "",
        "| seed | span | variant | days | outcome mismatches | trades main | trades ref | field mismatches | max abs dR | result |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    all_ok, reasons, exits, hand = True, Counter(), Counter(), []
    for seed in SEEDS:
        start, end = SPANS[seed]
        prim, part = generate(start, end, seed=seed, partner_seed=seed + 1000)
        mk, pk = build_market("NAS100", prim), build_market("SPX", part)
        rm, rp = RefMarket(prim, "NAS100"), RefMarket(part, "SPX")
        days = [d.date() for d in pd.bdate_range(pd.Timestamp(start) + pd.Timedelta(days=31), end)]
        for cfg, label in ((BASELINE, "A"), (EXPERIMENT_OTE, "B"), (EXPERIMENT_SMT, "SMT")):
            eng = Engine(mk, cfg, pk if cfg.smt_enabled else None)
            n_bad = n_fbad = n_main = n_ref = 0
            max_dr = 0.0
            for d in days:
                r_main = eng.run_day(d)
                r_reason, r_trade = run_day(
                    rm, d, model=cfg.entry_model, smt=rp if cfg.smt_enabled else None
                )
                reasons[(label, r_main.reason)] += 1
                if r_main.reason != r_reason:
                    n_bad += 1
                    if n_bad <= 5:
                        print(
                            f"  outcome mismatch seed {seed} {label} {d}: main={r_main.reason} ref={r_reason}"
                        )
                    continue
                if r_main.trade is None:
                    continue
                n_main += 1
                n_ref += 1
                mv = main_view(r_main.trade)
                exits[(label, mv["exit_reason"], mv["gap_through"])] += 1
                bad = [f for f in FIELDS if not same(mv[f], r_trade[f])]
                max_dr = max(max_dr, abs(mv["r"] - r_trade["r"]))
                if bad:
                    n_fbad += 1
                    print(f"  field mismatch seed {seed} {label} {d}: {bad}")
                if label == "A" and len(hand) < 6:
                    hand.append((seed, d, r_main.trade))
            ok = n_bad == 0 and n_fbad == 0 and max_dr < 1e-9
            all_ok &= ok
            lines.append(
                f"| {seed} | {start[:4]}-{end[:4]} | {label} | {len(days)} | {n_bad} | {n_main} | {n_ref} | "
                f"{n_fbad} | {max_dr:.1e} | {'MATCH' if ok else 'MISMATCH'} |"
            )
            print(lines[-1], flush=True)
    lines += [
        "",
        "## Outcome coverage (main engine, all seeds)",
        "",
        "| variant | outcome | days |",
        "|---|---|---|",
    ]
    lines += [f"| {k[0]} | {k[1]} | {v} |" for k, v in sorted(reasons.items())]
    lines += [
        "",
        "## Exit coverage (trades)",
        "",
        "| variant | exit | gap-through | trades |",
        "|---|---|---|---|",
    ]
    lines += [f"| {k[0]} | {k[1]} | {k[2]} | {v} |" for k, v in sorted(exits.items())]
    lines += ["", f"**Overall: {'MATCH' if all_ok else 'MISMATCH'}**", ""]
    (OUT / "reference_check.md").write_text("\n".join(lines), "utf-8")
    write_hand_check(hand)
    return 0 if all_ok else 1


def write_hand_check(hand: list[tuple[int, dt.date, dict]]) -> None:
    out = [
        "# Cycle 21 hand-check table (synthetic seeds, variant A)",
        "",
        "Each row can be recomputed by hand: 1R = |limit - stop| + 0.5; target needs |target - limit| >= 2R;",
        "R = ((exit - limit) x side) / 1R. Stop exits = stop -/+ 0.5 unless the bar opened beyond the stop.",
        "",
        "| seed | date | side | bias | ref (price) | sweep 5m start / extreme | MSS close time / broken swing | FVG [bottom, top] | limit | stop | 1R | target (name) | planned R:R | fill | exit time / reason / price | R | R recomputed |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for seed, d, t in hand:
        unit = abs(t["limit"] - t["stop"]) + 0.5
        r_hand = ((t["exit_price"] - t["limit"]) * t["side"]) / unit
        out.append(
            f"| {seed} | {d} | {t['side']:+d} | {t['htf_bias']} | {t['liquidity_ref']} ({t['liquidity_ref_price']:.2f}) | "
            f"{t['sweep_ts'][11:16]} / {t['sweep_price']:.2f} | {t['mss_ts'][11:16]} / {t['mss_broken_swing']:.2f} | "
            f"[{t['fvg_bottom']:.3f}, {t['fvg_top']:.3f}] | {t['limit']:.3f} | {t['stop']:.3f} | {unit:.3f} | "
            f"{t['target']:.3f} ({t['target_name']}) | {t['planned_rr']:.2f} | {t['fill_ts'][11:16]} | "
            f"{t['exit_ts'][11:16]} / {t['exit_reason']} / {t['exit_price']:.3f} | {t['r']:+.4f} | {r_hand:+.4f} |"
        )
    (OUT / "hand_check.md").write_text("\n".join(out) + "\n", "utf-8")


if __name__ == "__main__":
    sys.exit(run())
