"""Gate 6: event-level parity between the frozen engine ledger and the independent reference trace (spec §7).

Both sides are reduced to one canonical stream: (stage, time_ns, *values) for the decision stages, then the final
result. Floats are compared with an absolute tolerance; strings and times must match exactly.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from v17.c23_visual.models import VisualEvent

CANON_STAGES = (
    "sweep",
    "mss",
    "fvg",
    "order_created",
    "order_expired_cancelled",
    "order_filled",
    "exit",
)
FIELDS: dict[str, tuple[str, ...]] = {
    "sweep": ("ref", "ref_price", "extreme"),
    "mss": ("broken_swing",),
    "fvg": ("bottom", "top"),
    "order_created": ("limit", "stop", "target_name", "target"),
    "order_expired_cancelled": (),
    "order_filled": ("price",),
    "exit": ("reason", "price"),
}
Canon = tuple[object, ...]


def engine_stream(ledger: Sequence[VisualEvent], result: str) -> list[Canon]:
    out: list[Canon] = []
    for e in ledger:
        if e.stage in CANON_STAGES and e.event_time is not None:
            t = int(pd.Timestamp(e.event_time).value)
            out.append((e.stage, t, *(e.payload.get(k) for k in FIELDS[e.stage])))
    out.append(("result", result))
    return out


def _py(v: object) -> object:
    item = getattr(v, "item", None)  # numpy scalar -> Python scalar
    return item() if callable(item) else v


def reference_stream(trace: Sequence[tuple[object, ...]], result: str) -> list[Canon]:
    out: list[Canon] = [tuple(_py(v) for v in x) for x in trace]
    out.append(("result", result))
    return out


def _same(a: object, b: object, tol: float) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or (isinstance(a, int) and isinstance(b, int)):
        return a == b  # times (epoch ns) and flags: exact
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        fa, fb = float(a), float(b)
        return (math.isnan(fa) and math.isnan(fb)) or abs(fa - fb) <= tol
    return a == b


def compare(eng: list[Canon], ref: list[Canon], tol: float = 1e-9) -> list[str]:
    """Empty list = exact parity. Otherwise one message per differing position."""
    bad: list[str] = []
    if len(eng) != len(ref):
        bad.append(f"length {len(eng)} vs {len(ref)}")
    for k, (a, b) in enumerate(zip(eng, ref, strict=False)):
        if len(a) != len(b) or not all(_same(x, y, tol) for x, y in zip(a, b, strict=True)):
            bad.append(f"#{k}: engine {a} != reference {b}")
    return bad
