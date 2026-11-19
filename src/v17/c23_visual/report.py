"""Automated disagreement + metric report (spec §5 of the pasted plan, §6-§7 here). Report-only: nothing here feeds
back into strategy rules."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from v17.c23_visual.metrics import METRICS_VERSION, CandidateMetrics
from v17.c23_visual.models import DayRecord

METRIC_COLS = ("sweep_depth", "disp_body_ratio", "disp_range_atr", "fvg_size_atr")


@dataclass
class DayRow:
    instrument: str
    variant: str
    trading_date: str
    category: str
    engine_result: str
    reference_result: str
    parity_ok: bool
    mismatch: str
    r: float = math.nan
    metrics: dict[str, float | bool | None] = field(default_factory=dict)


def row(
    rec: DayRecord,
    variant: str,
    ref_result: str,
    mismatches: list[str],
    r: float,
    m: CandidateMetrics,
) -> DayRow:
    return DayRow(
        rec.instrument,
        variant,
        rec.trading_date,
        rec.category,
        rec.result,
        ref_result,
        not mismatches,
        "; ".join(mismatches[:3]),
        r,
        m.as_dict(),
    )


def frame(rows: list[DayRow]) -> pd.DataFrame:
    base = pd.DataFrame([{k: v for k, v in r.__dict__.items() if k != "metrics"} for r in rows])
    mets = pd.DataFrame([r.metrics for r in rows])
    return pd.concat([base, mets], axis=1)


def _med(s: pd.Series) -> str:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return f"{float(np.median(s)):.3f} (n={len(s)})" if len(s) else "-"


def markdown(df: pd.DataFrame, title: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"Metrics version `{METRICS_VERSION}` — descriptive only, never a filter.",
        "",
    ]
    lines += ["## Event parity (engine vs independent reference)", ""]
    lines += [
        "| instrument | variant | days | event-level mismatches | parity |",
        "|---|---|---|---|---|",
    ]
    for (inst, var), g in df.groupby(["instrument", "variant"], sort=True):
        bad = int((~g.parity_ok).sum())
        lines.append(f"| {inst} | {var} | {len(g)} | {bad} | {'PASS' if bad == 0 else 'FAIL'} |")
    lines += ["", "## Coverage by category", "", "| category | days |", "|---|---|"]
    for k, v in sorted(Counter(df.category).items()):
        lines.append(f"| {k} | {v} |")
    charted = df[df.category.isin(["filled", "unfilled_expired", "rejected_after_sweep"])]
    lines += [
        "",
        "## Near-miss / rejection reasons after a sweep",
        "",
        "| reason | days |",
        "|---|---|",
    ]
    for k, v in Counter(charted.engine_result).most_common():
        lines.append(f"| {k} | {v} |")
    trades = df[df.category == "filled"]
    win, loss = trades[trades.r > 0], trades[trades.r <= 0]
    lines += ["", "## Metric medians: winners vs losers (filled trades)", ""]
    lines += ["| metric | winners | losers |", "|---|---|---|"]
    for c in METRIC_COLS:
        lines.append(f"| {c} | {_med(win[c])} | {_med(loss[c])} |")
    if "sweep_close_inside" in trades:
        sci = trades.sweep_close_inside.dropna()
        lines.append(
            f"| sweep_close_inside (share true) | {sci.mean():.3f} (n={len(sci)}) | |"
            if len(sci)
            else ""
        )
    lines += ["", "## Disagreements (first 20)", ""]
    dis = df[~df.parity_ok].head(20)
    if dis.empty:
        lines.append("None.")
    else:
        lines += [
            "| instrument | variant | date | engine | reference | detail |",
            "|---|---|---|---|---|---|",
        ]
        for _, r in dis.iterrows():
            lines.append(
                f"| {r.instrument} | {r.variant} | {r.trading_date} | {r.engine_result} | {r.reference_result} | {r.mismatch} |"
            )
    return "\n".join(lines) + "\n"
