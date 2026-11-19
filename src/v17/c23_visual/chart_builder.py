"""Four-panel candlestick rendering (D1 / 15m / 5m / M1) for decision and outcome views (spec §5).

Candles are selected by close time: the decision view never contains a candle that closes after the cut.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle

from v17.c23_visual.annotations import decision_view
from v17.c23_visual.models import Annotation, DayRecord, Timeframe
from v17.smc_sb.data import Market
from v17.smc_sb.session import NS_PER_MIN, ny_ns

View = Literal["decision", "outcome"]
PANELS: tuple[Timeframe, ...] = ("D1", "15m", "5m", "1m")
COLORS = {"up": "#2e7d32", "down": "#c62828", "ann": "#1565c0", "box": "#ffb300", "out": "#6a1b9a"}


@dataclass(frozen=True)
class Candles:
    start: np.ndarray  # epoch ns
    end: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray  # noqa: E741
    c: np.ndarray


def _frame(df: pd.DataFrame, lo: int, hi: int) -> Candles:
    m = (df.start.to_numpy() >= lo) & (df.end.to_numpy() <= hi)
    s = df[m]
    return Candles(*(s[k].to_numpy() for k in ("start", "end", "o", "h", "l", "c")))


def panel_candles(mk: Market, rec: DayRecord, view: View) -> dict[Timeframe, Candles]:
    """Candles per panel. Decision view: closes <= cut; outcome view: closes <= end (+ short tail)."""
    assert rec.cut_ns is not None
    assert rec.end_ns is not None
    day = pd.Timestamp(rec.trading_date).date()
    hi = (
        rec.cut_ns if view == "decision" else min(rec.end_ns + 15 * NS_PER_MIN, ny_ns(day, "16:00"))
    )
    d = mk.daily
    dstart = (
        np.array([ny_ns(x.date(), "17:00") for x in d.index], dtype=np.int64) - 24 * 60 * NS_PER_MIN
    )
    dend = dstart + 24 * 60 * NS_PER_MIN
    daily = pd.DataFrame(
        {
            "start": dstart,
            "end": dend,
            "o": d.o.to_numpy(),
            "h": d.h.to_numpy(),
            "l": d.l.to_numpy(),
            "c": d.c.to_numpy(),
        }
    )
    daily = daily[daily.end <= hi].tail(20)
    m1 = pd.DataFrame(
        {"start": mk.ts, "end": mk.ts + NS_PER_MIN, **{k: mk.mid[k] for k in ("o", "h", "l", "c")}}
    )
    m1_lo = (rec.cut_ns - 30 * NS_PER_MIN) if view == "decision" else (rec.cut_ns - 15 * NS_PER_MIN)
    return {
        "D1": _frame(daily, int(daily.start.min()) if len(daily) else 0, hi),
        "15m": _frame(mk.c15, ny_ns(day, "07:00"), hi),
        "5m": _frame(mk.c5, ny_ns(day, "09:00"), hi),
        "1m": _frame(m1, m1_lo, hi),
    }


def _x(c: Candles, t: int) -> float:
    """Position of time t on a panel whose x axis is candle index (no gaps)."""
    if len(c.start) == 0:
        return 0.0
    return float(np.searchsorted(c.start, t, side="right") - 1)


def _draw(ax: Axes, c: Candles, annos: list[Annotation], title: str) -> None:
    for i in range(len(c.start)):
        up = c.c[i] >= c.o[i]
        col = COLORS["up"] if up else COLORS["down"]
        ax.vlines(i, c.l[i], c.h[i], color=col, linewidth=0.8)
        ax.add_patch(
            Rectangle(
                (i - 0.35, min(c.o[i], c.c[i])), 0.7, max(abs(c.c[i] - c.o[i]), 1e-9), color=col
            )
        )
    for a in annos:
        x0, x1 = _x(c, a.t0), max(_x(c, a.t1), _x(c, a.t0))
        col = COLORS["out"] if a.outcome_only else COLORS["ann"]
        if a.kind == "hline":
            ax.hlines(
                a.p0, max(x0, -0.5), max(x1, x0) + 0.5, color=col, linewidth=0.9, linestyles="--"
            )
            ax.text(max(x0, -0.5), a.p0, a.label, fontsize=6, color=col, va="bottom")
        elif a.kind == "box":
            ax.add_patch(
                Rectangle(
                    (x0 - 0.4, a.p0), x1 - x0 + 0.8, a.p1 - a.p0, color=COLORS["box"], alpha=0.3
                )
            )
            ax.text(x0, a.p1, a.label, fontsize=6, color="#e65100", va="bottom")
        elif a.kind == "vspan":
            ax.axvspan(x0 - 0.45, x0 + 0.45, color=COLORS["box"], alpha=0.15)
        else:
            ax.plot([x0], [a.p0], marker="o", markersize=4, color=col)
            ax.text(x0, a.p0, " " + a.label, fontsize=6, color=col)
    ax.set_title(title, fontsize=8)
    ax.tick_params(labelsize=6)
    if len(c.start):
        step = max(1, len(c.start) // 6)
        idx = list(range(0, len(c.start), step))
        fmt = "%m-%d" if title.startswith("D1") else "%H:%M"
        ax.set_xticks(
            idx,
            [
                pd.Timestamp(int(c.start[i]), tz="UTC").tz_convert("America/New_York").strftime(fmt)
                for i in idx
            ],
        )
        ax.set_xlim(-1, len(c.start))


def view_annotations(annos: list[Annotation], rec: DayRecord, view: View) -> list[Annotation]:
    assert rec.cut_ns is not None
    return decision_view(annos, rec.cut_ns) if view == "decision" else list(annos)


def render(mk: Market, rec: DayRecord, annos: list[Annotation], view: View, path: Path) -> str:
    """Render one view to PNG; returns the PNG sha256 (first 16 hex)."""
    candles = panel_candles(mk, rec, view)
    shown = view_annotations(annos, rec, view)
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), dpi=100)
    for ax, p in zip(axes.flat, PANELS, strict=True):
        _draw(
            ax,
            candles[p],
            [a for a in shown if a.panel == p],
            f"{p} {'(decision time)' if view == 'decision' else '(outcome)'}",
        )
    head = f"{rec.instrument} {rec.trading_date}  c23 {view}"
    if view == "outcome":
        head += f"  result={rec.result}"
    fig.suptitle(head, fontsize=10)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="png", metadata={"Software": None})
    plt.close(fig)
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
