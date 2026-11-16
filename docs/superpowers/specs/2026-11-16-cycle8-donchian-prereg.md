# Cycle 8 — Donchian Channel Breakout (pre-registration)

**Date:** 2026-11-16
**Branch:** `cycle8-donchian-trend` off `cycle7-gap-continuation-spx` HEAD `057e6a4`.
**Role in ensemble plan:** candidate #4.

## 1. Hypothesis

Trend-persistence on non-equity asset classes (WTI crude, Dollar Index) rewards channel-breakout entries. Donchian is the classical turtle entry; well-documented since 1980s. Cycles 1-3 shelved on equity indices; adding a non-index asset is the ensemble-correlation play.

## 2. Instruments and data

Both run independently and independently gated.

| symbol | source CSV | dev slice | holdout slice |
|---|---|---|---|
| `LIGHTCMDUSD` (WTI crude oil) | `LIGHTCMDUSD_1 Min_{Bid,Ask}_2015.01.01_2026.11.16.csv` | 2015-01-01 → 2023-12-31 | 2024-01-01 → 2026-11-16 |
| `DOLLARIDXUSD` (Dollar Index) | `DOLLARIDXUSD_1 Min_{Bid,Ask}_2017.12.01_2026.11.16.csv` | **2018-01-01 → 2023-12-31** (data starts 2017-12) | 2024-01-01 → 2026-11-16 |

Ingested to `data/bars_m1_paired/{LIGHTCMDUSD,DOLLARIDXUSD}/year=YYYY/`.

D1 built in-memory per symbol by UTC-day resample of M1 paired (Donchian is close-to-close; no session alignment needed).

**Pre-reg deviation note.** DXY dev window is 6 years vs WTI's 9 years. Per-symbol gates evaluated at each window; no cross-symbol borrowing of data.

## 3. Signal

Let `H_entry[T-1]` = max high over the last `lookback_entry` D1 bars ending at `T-1`; `L_entry[T-1]` = corresponding min low. `H_exit`, `L_exit` same but with `lookback_exit`.

- **Long entry**: `close[T] > H_entry[T-1]`. Fill at next bar's open (`ask_o[T+1]`).
- **Short entry**: `close[T] < L_entry[T-1]`. Fill at next bar's open (`bid_o[T+1]`).
- **Long exit**: next bar where `close < L_exit[T-1]`. Fill at exit bar's next open.
- **Short exit**: next bar where `close > H_exit[T-1]`. Same.
- **Position**: single position per symbol. Flat flip on opposite signal.

No stop other than opposite-channel exit.

## 4. Grid (locked before any backtest)

| param | values |
|---|---|
| `lookback_entry` | 20, 40, 55 |
| `lookback_exit` | 10, 20 |
| `direction` | `long_only`, `short_only`, `both` |

= 18 configs per symbol × 2 symbols = 36 config-slots total.

## 5. Risk accounting (R unit)

- R unit = `ATR20_prev × lots × point_value` at entry (static; locked at fill time).
- Per-trade PnL in R = `(exit_px - entry_px) / (ATR20_prev)` for long, inverted for short.
- No compounding at grid phase; sum-of-R only.

## 6. Costs

- Long fills at ask, short fills at bid (spread already in paired bars).
- No additional slippage at grid phase. Sensitivity rerun at +1 point only if base passes.
- No commission (FTMO CFD-style).

## 7. Gate (locked; no loosening)

**Tier 1 — dev gate per (symbol × config):**
- PF ≥ 1.3.
- Trade count ≥ 30 over dev (Donchian is low-frequency).
- Max drawdown ≤ 8R (Donchian is trend-follow; drawdowns are wider by design).
- Sharpe ≥ 0.

**Tier 2 — scheme-1 MCPT** on survivors. 500 permutations. Dev p ≤ 0.05.

**Tier 3 — Bonferroni** across 36 slots: per-slot α ≤ 0.05 / 36 ≈ 0.0014.

**Tier 4 — holdout confirmation** on each Bonferroni-surviving slot: holdout PF ≥ 1.2, holdout MCPT p ≤ 0.05.

Fail at any tier ⇒ SHELVE that slot. If both symbols shelve ⇒ candidate #4 SHELVED.

## 8. Pre-reg hard stop

If zero slots pass Tier 1 across both symbols ⇒ SHELVE same session.

## 9. Artifacts

- `scripts/run_c8_donchian_grid.py` — grid runner (M1 → D1 UTC resample → Donchian backtest).
- `out/c8/dev_grid_{SYMBOL}.csv` — per-symbol grid.
- `out/c8/dev_grid.log` — run log.

## 10. Non-goals

- No volatility filter, no regime filter, no ATR-based position sizing (keep R-unit static).
- No pyramiding.
- No long-only bias except via `direction` grid axis.
- No FTMO-breaker simulation at grid phase.
