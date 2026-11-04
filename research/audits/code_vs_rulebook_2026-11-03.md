# Audit 2 — Code vs Rulebook
**Date:** 2026-11-04
**Spec:** docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md section 13.1
**Rulebook:** research/ict/ICT_STRATEGY_RULEBOOK.md
**Verdict:** BLOCK — 2 CRITICAL, 3 HIGH. 4 items are MUST_FIX before gate run.

---

## CRITICAL

### C-1 MUST_FIX — Aggressive entry side inverted (SB-04 violation)
File: src/v17/setups/silver_bullet_fsm.py:93-95
Rule SB-04 Model 2: proximal edge of FVG. Rulebook: proximal = L_3 for bullish, H_3 for bearish.
For a bullish FVG at bar i: bottom = H_{i-2}, top = L_i. Proximal edge (price re-enters from below) is bottom.
Code: `entry = top if side == "LONG" else bottom`
This places the LONG limit at top (= L_i, distal edge). Price touches bottom first; order never fills
until the gap is fully covered. Every LONG aggressive entry fires at wrong price.
Fix: `entry = bottom if side == "LONG" else top`

### C-2 MUST_FIX — SB-02 M15 swing pool omitted with no confirmed runtime replacement
File: src/v17/structure/liquidity_pools.py:7-9 (docstring)
Rule SB-02: three pool sources — (1) session extreme, (2) prev-hour H/L, (3) M15 swing last 45 min.
Module omits source 3, citing Task 5.3 engine runner. No Task-5.3 code is in audit scope.
FSM context key sweep_confirmed has no confirmed M15-swing supplier.
Impact: any setup needing an M15 sweep never forms; trade count may fall below Gate G2 (50 trades).
Fix: wire M15 swing pools before gate run, or document the omission as a frozen approved scope
reduction with an estimated trade-count impact.

---

## HIGH

### H-1 — compute_d1_bias column contract unspecified (KeyError risk)
File: src/v17/structure/bias.py:149
Uses df["bid_c"] with no assertion. Missing column raises undecorated KeyError with no context.
Fix: add column-presence assertion with clear message, or accept close_col parameter.

### H-2 MUST_FIX — liquidity_pools.py .loc[idx, col] raises TypeError on non-unique index
File: src/v17/structure/liquidity_pools.py:30-31,35-36,48-49,53-54
idxmax() returns index label; after slicing without reset_index the label can match multiple rows.
float(Series) raises TypeError at runtime. mypy reports 16 errors in this file.
Fix: replace .loc[hi_idx, col] with .at[hi_idx, col] throughout, or reset_index(drop=True) on each slice.

### H-3 — Mid-file module-level imports in bias.py (ruff E402)
File: src/v17/structure/bias.py:108-110
from typing import Literal, import numpy, and sb_constants import appear after function definitions.
No runtime failure today, but complicates circular-import analysis and test isolation.
Fix: move all imports to top of file.

---

## MEDIUM

### M-1 MUST_FIX — SL min-distance floor re-anchors from entry, not sweep extreme
File: src/v17/setups/sb_sl_tp.py:62-64 (LONG), 81-83 (SHORT)
Rule JS-06: SL anchored beyond sweep_extreme. Initial raw_sl = sweep_extreme - buf_min is correct.
But floor guard then does: raw_sl = entry - buf_min
When entry is at CE (FVG midpoint), entry is well above sweep_extreme.
entry - buf_min can exceed sweep_extreme, making SL tighter than the extreme.
Fix: remove the raw_sl = entry - buf_min line. Keep raw_sl at sweep_extreme - buf_min; only update distance.

### M-2 — SHORT reject message wrong polarity
File: src/v17/setups/sb_sl_tp.py:87
Message says "not above entry for SHORT" but SHORT target must be below entry.
Fix: change to "is not below entry for SHORT".

### M-3 — Bearish FVG top/bottom naming convention risk
File: src/v17/structure/fvg_sb.py:39-43
No correctness bug; CE calculation is correct. But top = L_{i-2} is the proximal edge for bearish,
not bottom. Add a comment clarifying which edge is proximal to prevent future caller confusion.

### M-4 — SpreadGuard silently allows all entries when history is empty
File: src/v17/data/spread_guard.py:39-41
Returns False (allow) when no minute-of-day history exists. First 30 days of each symbol run
unguarded. No log line means the backtest audit cannot count unguarded bars.
Fix: add logging.warning on the empty branch.

### M-5 — instrument_spec.pip_size silently defaults to 0.0001 for unknown symbols
File: src/v17/common/instrument_spec.py:26-28
Any symbol not in _PIP_SCALE returns 0.0001. SL/TP silently miscalculates for new symbols.
Fix: raise ValueError for unknown symbols, or log a warning.

---

## LOW

### L-1 — Import order violations (ruff I001) in 5 files
blackout.py, spread_guard.py, sb_sl_tp.py, silver_bullet_fsm.py, bias.py
Run: ruff check --fix

### L-2 — Ambiguous variable l in displacement.py:20 (ruff E741)
Rename to low_ or bar_low.

### L-3 — Line-length violations in sb_engines.py:20-21 (ruff E501)
Lines 109 chars vs 100-char limit. Cosmetic.

### L-4 — Missing -> None on __init__ methods
silver_bullet_fsm.py:46, spread_guard.py:17. Auto-fixable.

### L-5 — Untyped dict in function signatures (mypy type-arg errors)
fvg_sb.py, displacement.py, silver_bullet_fsm.py, liquidity_pools.py.
22 mypy errors total. Use dict[str, Any] or typed dataclasses.

---

## Rule Coverage Matrix

Rule                                  | Module                   | Status
SB-01 windows/symbols                 | sb_engines.py            | PASS
SB-02 session + prev-hour pools       | liquidity_pools.py       | PASS
SB-02 M15 swing pool                  | liquidity_pools.py       | PARTIAL (C-2)
SB-03 displacement body ratio + ATR   | displacement.py          | PASS
SB-04 FVG formula + CE                | fvg_sb.py                | PASS
SB-04 aggressive entry proximal edge  | silver_bullet_fsm.py     | FAIL (C-1)
SB-04 FVG cost viability >= 2x spread | silver_bullet_fsm.py     | PASS
SB-05 R:R >= 1.5 reject gate          | sb_sl_tp.py              | PASS
SB-05 fallback targets from constants | sb_sl_tp.py              | PASS
SB-A1 D1 bias EMA20 + structure       | bias.py:compute_d1_bias  | PASS
SB-A1 causality (< as_of_utc_ns)      | bias.py:compute_d1_bias  | PASS
P-04 FVG definition                   | fvg_sb.py                | PASS
P-04 CE midpoint                      | fvg_sb.py                | PASS
JS-06 SL beyond sweep extreme         | sb_sl_tp.py              | FAIL (M-1)
No Asian fallback (SB-02 Prohibition) | liquidity_pools.py       | PASS
Causality across all modules          | all                      | PASS
Pip scaling via instrument_spec       | sb_sl_tp.py              | PASS
Determinism (no time.time/random)     | all                      | PASS
Constants from sb_constants           | all logic modules        | PASS
Specific exceptions (SBRejectError)   | sb_sl_tp.py              | PASS

---

## Severity Summary

Severity | Count
---------|------
CRITICAL |   2
HIGH     |   3
MEDIUM   |   5
LOW      |   5

MUST_FIX (gate blockers): C-1, C-2, H-2, M-1
