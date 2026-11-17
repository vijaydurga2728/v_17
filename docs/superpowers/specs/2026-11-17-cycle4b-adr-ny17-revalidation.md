# Cycle 4B ADR — RSI2-NAS100 revalidation on broker-aligned (NY 17:00) daily bars

**Status:** FROZEN 2026-11-17 (user: "proceed"). Committed before any RSI2 result on the rebuilt bars.
**Branch:** `cycle12-rsi2-fx-majors` (current HEAD; the change is a data-construction fix to cycle 4B).

## Problem

Cycle 4B validated RSI2-NAS100 on `data/bars_d1/USATECHIDXUSD/` built on **UTC midnight** days
(`scripts/build_d1_cache.py`, whose docstring already flagged this as an approximation for RSI(2)). That cache holds
~611 Sunday stub bars plus holiday stubs. The live demo trades IC Markets MT5 `USTEC` D1 bars, which have none.

**Alignment evidence (price bars only, no strategy run), 2024-01-02..2026-10-13:**
- MT5 USTEC D1: 721 bars, Monday-Friday only. MT5 H1 shows the broker session runs 18:00 → 17:00 ET.
- Dukascopy rebuilt on the **17:00 ET rollover**: 719 matched dates, 0 extra dates, daily-return correlation 0.972.
  Rollovers from 16:15 to 18:00 ET give identical bars.
- Existing UTC cache: 149 extra dates (stubs), correlation 0.960.

## Decision

1. Rebuild NAS100 D1 from the cycle 4B M1 source (`.worktrees/sb-6-engine-gate/data`) with
   `v17.setups.c12_rsi2_fx.build_fxny_d1` (17:00 ET rollover, Mon-Fri, labelled by closing day; `ts_utc` = closing
   day 00:00 UTC). Partitions: dev ≤ 2024, holdout 2025+.
2. Run the four cycle 4B scripts **unchanged** (`run_c4b_gates.py`, `run_c4b_holdout.py`,
   `run_c4b_scheme1_mcpt.py`, `run_c4b_paired_mcpt.py`) in a temporary worktree whose `data/bars_d1/USATECHIDXUSD/`
   is replaced by the rebuilt bars. RSI2 rules, seeds, 500 permutations and windows are unchanged.
3. Also report the scheme-1 mean-R p-value with 10,000 permutations and the +1 correction.

## Pass criteria (the standard RSI2-NAS100 was advanced on, stated in advance)

- Dev: G1, G2, G4, G5 pass (G3 reported).
- Holdout (2025-01-01 → 2026-10-18): PF ≥ 1.3, WR ≥ 50%, max DD < 10R, no FTMO hard freeze.
- Scheme-1 luck test, statistic **mean R**: p < 0.05 on dev **and** holdout.
- Paired-alpha luck test: p_cum < 0.05 on dev and holdout.

**PASS** → the demo continues, now backed by broker-aligned validation.
**FAIL on any criterion** → recommend stopping the demo and not paying any FTMO fee; RSI2-NAS100 is SHELVED.

## Limits

- The holdout was already inspected on UTC bars in cycle 4B, so this is a robustness re-check, not fresh evidence.
- Feed differences (Dukascopy vs IC Markets, ~12 pt median close difference) remain.
