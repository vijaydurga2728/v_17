# Multi-Symbol Expansion Handoff — Next Session

**Session end state:** v17 code supports multi-symbol ingest and backtest. Config stubs added for Tier 1 + 2 symbols. CSVs identified. NO new symbols ingested or backtested yet.

**Why this expansion:** GBP alone generates ~10 trades/yr with PF 1.29 — real edge but 83× short of FTMO Phase 1 target (10%/mo). Multi-symbol expansion is the only honest path to the required signal frequency.

---

## What was done this session

| File | Change |
|---|---|
| `src/v17/backtest/cost.py` | Added `COST_MODEL` entries for `EURGBP`, `USATECHIDXUSD`, `USDJPY`, `AUDUSD`. Added `PIP_SCALE` + `PIP_VALUE_PER_LOT` dicts for 11 symbols. **Placeholder spreads — must be verified against user's FTMO Normal dashboard.** |
| `src/v17/data/calendar/blackout.py` | `AFFECTED` map expanded to 11 symbols with correct currency sets (indices → `{USD}`). |
| `src/v17/data/dukascopy_csv.py` | `_pip_scale(sample_price, symbol=None)` is now symbol-aware. JPY→100, index→1, FX→10000. Legacy price-magnitude fallback preserved. `stitch_pair(bids, asks, symbol=None)` accepts symbol. |
| `src/v17/data/cli.py` | `ingest()` passes symbol to `stitch_pair`. |
| `scripts/ingest_user_csvs.py` | Batch ingester reads from `C:/Users/Vijayakumar R/Documents` by default. CLI: `python scripts/ingest_user_csvs.py [csv_dir] [sym1 sym2 ...]`. Defaults to Tier 1. |

**Tests: 337 passing.** No regressions.

---

## Blockers for next session — user input required

### 1. FTMO Normal spreads (CRITICAL — placeholder values in code)

Open user's FTMO Normal account dashboard. Record typical London/NY-session average spread for each symbol. Format:

```
EURGBP  = ? pips
USATECHIDXUSD (NAS100) = ? points
USDJPY  = ? pips
AUDUSD  = ? pips
```

Update `COST_MODEL` in `src/v17/backtest/cost.py` with real values before any backtest claim. Current placeholders are safe for ingest+smoke, NOT for edge measurement.

### 2. pip_value_per_lot for indices

Current placeholder:
- `USATECHIDXUSD` → $1/point/lot
- `USA500IDXUSD` → $5/point/lot
- `USA30IDXUSD` → $1/point/lot

Verify from FTMO contract specs. If wrong, lot-sizing calculations will be off by that ratio.

### 3. GBPJPY data missing

User requested GBPJPY as Tier 1. Not in CSV inventory. Options:
- (a) User downloads GBPJPY from Dukascopy manually.
- (b) Skip GBPJPY, use USDJPY instead.
- (c) Synthesize GBPJPY = GBPUSD × USDJPY (cross-rate; introduces compounded spread).

Default assumption without user override: **(b) USDJPY instead**.

### 4. Risk engine per-symbol pip_value

`RISK["pip_value_per_lot_usd"]` in `src/v17/risk/risk_rules.py` is a single value (`$10`). Risk engine needs to look up by symbol from `PIP_VALUE_PER_LOT` dict. **Not yet wired.** 20-line change: pass symbol to risk engine, lookup instead of static value.

---

## Execution plan for next session

### Phase 0: User confirms blockers above (10 min)

### Phase 1: Ingest Tier 1 (30-60 min)

```powershell
cd "C:\personal\v_17"
& ".venv\Scripts\python.exe" scripts\ingest_user_csvs.py
```

Verify parquet appears under `data/parquet/EURGBP/1m/year=*/` and `data/parquet/USATECHIDXUSD/1m/year=*/`.

### Phase 2: Risk engine per-symbol pip_value (20 min)

Wire `PIP_VALUE_PER_LOT` into `DefaultRiskEngine`. Pass symbol via `signal.symbol`. Update test fixtures.

### Phase 3: Backtest Tier 1 2015-2024 (parallel, 10-30 min)

```powershell
& ".venv\Scripts\python.exe" -m v17.cli backtest --symbol EURGBP --from 2015-01-01 --to 2024-12-31 --seed 42
& ".venv\Scripts\python.exe" -m v17.cli backtest --symbol USATECHIDXUSD --from 2015-01-01 --to 2024-12-31 --seed 42
```

### Phase 4: Evaluate — honest per-symbol PF across 2 periods (2015-2017 vs 2021-2024)

- Any symbol with PF ≥ 1.2 across BOTH periods → add to live roster
- Any symbol with PF < 1.0 either period → exclude from live
- Report: trade count, PF, DD, Sharpe per symbol per period

### Phase 5 (conditional): Combined portfolio simulation

If 2-3 symbols pass Phase 4, write portfolio-mode EventLoop:
- Share AccountState across symbols
- Enforce `max_concurrent_positions=3` across all symbols combined
- `max_trades_per_day=3` globally
- Separate per-symbol daily P&L lockout but single global DD

Expected signal frequency boost: 3 symbols × 10 trades/yr/symbol = 30/yr. Still below OOS=200 but closer.

### Phase 6 (conditional): FTMO challenge simulation

- Pick best-N-symbols portfolio
- Simulate 30-day sliding window: can we hit +10% within any window?
- Report windows passed / total windows across 2015-2024

---

## Honest expectation

GBP PF 1.29 is a real but thin edge. Adding more symbols will:
- (likely) 2-3 symbols reach the same PF ≥ 1.2 threshold (correlated with GBP: EURGBP, maybe NAS100 via US-session momentum)
- (likely) 4-5 symbols fail like EUR

Even with 3 edge-bearing symbols at 10 trades/yr each = 30 trades/yr combined. At PF 1.29 and 1% per trade, expected monthly ~0.3% × 2.5 = 0.75%/mo. **Still below FTMO 10% monthly target.** The honest path to 10% monthly:
- Multi-symbol × higher per-trade risk (risk 2% instead of 1% once DD proven safe)
- OR shorter timeframe (5m zones producing 3× signals per bar)
- OR add 1h/4h setup variants

Expect next session to answer: "which symbols pass, how much does per-trade risk headroom permit."

---

## Files to review before touching code next session

- `docs/RULES.md` — 52 pass/fail rules for profitability claim
- `docs/prompts/find-profitable-system.md` — research-brief guardrails
- `docs/HANDOFF_MULTI_SYMBOL.md` — this file
- `src/v17/backtest/cost.py` — spread + pip_value configs
- `src/v17/risk/risk_rules.py` — current `pip_value_per_lot_usd=10` hardcoded (needs per-symbol wire)
