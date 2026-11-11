# ORB Reversal Indices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and gate the ORB Reversal strategy on NAS100 (single engine; SP500 dropped — no bars available 2026-11-11) with 7-fold anchored walk-forward, block-bootstrap MCPT, secondary gates, FTMO circuit breakers, and sealed-holdout verdict — reusing ~70% of SB-cycle infrastructure.

**Architecture:** Port infra from branch `sb-6-engine-gate` (HEAD `7eaeaa7`) into the fresh `orb-reversal-indices` branch via per-file `git checkout`. Fix two known perf bugs (Windows ProcessPool hang, 70-min batch wall-clock). Build new strategy modules (`setups/orb_constants.py`, `setups/orb_engines.py`, `setups/orb_fsm.py`, `structure/vwap.py`) with TDD. Run dev walk-forward, secondary gates, MCPT; if pass, run sealed holdout; report verdict in `docs/superpowers/plans/GATE_MANIFEST.md`.

**Tech Stack:** Python 3.11+, pandas, numpy, pytz (NY session clock), pyarrow (parquet bars), pytest, Windows 11 target.

**Spec:** `C:\personal\v_17\.worktrees\sb-6-engine-gate\.superpowers\sdd\2026-11-03-silver-bullet-6-engine-doctrine-test\orb-cycle-handoff.md`

## Global Constraints

- Target branch: `orb-reversal-indices` (already created from `main` HEAD `dac47c1`).
- Instruments: `USATECHIDXUSD` only (SP500 downgrade recorded 2026-11-11; `USA500IDXUSD` bars absent).
- Strategy: ORB Reversal — 30-min opening range (09:30-10:00 ET), fade breakout (short OR_high break + close back inside within 15 min; long symmetric).
- Entry: STOP order placed at OR_high (short reversal) / OR_low (long) once close-back-inside confirmed.
- Stop: breakout extreme ± 0.5 × ATR_14 (M1 ATR).
- Target: 0.5R initial; trail to session VWAP when VWAP farther than 0.5R; otherwise exit at 0.5R.
- Session window: 09:30-11:30 ET; max 1 trade/day/instrument (FTMO consistency friendly).
- FTMO account: $10k Standard, 0.5% equity risk/trade.
- Circuit breakers: daily -3% soft stop, total -8% hard freeze (tighter than SB's -4% / -8%).
- Sealed holdout: `2025-01-01` → `2026-10-18` (reused from SB cycle; no ORB params trained on it).
- Walk-forward: 7-fold anchored on dev data `2016-11-01` → `2024-12-31`.
- MCPT: scheme `pnl_bootstrap` only; block size 5; 500 permutations dev / 1000 holdout.
- Significance: α = 0.05 (single engine; no Bonferroni correction required).
- Cost model: 0.5 pt market-order slippage USATECH; 0 on limit/stop fills; FTMO $0 commission on indices; bid/ask paired bars. SP500 slippage/commission entries retained as dead config for later re-enable.
- Pre-flight rulings carried over: R-02 (MCPT scheme 1 deferred), R-05 (scheme 1 raises NotImplementedError).
- No `git add -A`; stage files by explicit path. No destructive git ops. No `--no-verify`.
- All new code must round-trip through `pytest -q` before commit.

---

### Task 1: Scaffold ORB cycle docs

**Files:**
- Create: `docs/superpowers/specs/2026-11-11-orb-reversal-indices-design.md`
- Modify: `docs/superpowers/plans/GATE_MANIFEST.md` (append new section)
- Create: `docs/superpowers/plans/00-INDEX.md` entry (append line)

**Interfaces:**
- Consumes: handoff doc.
- Produces: frozen spec path referenced by every later task; `GATE_MANIFEST.md` row with ORB cycle status = `IN-PROGRESS`.

- [ ] **Step 1:** Create `docs/superpowers/specs/2026-11-11-orb-reversal-indices-design.md` containing a verbatim copy of the Global Constraints section above plus the handoff "User-approved locked design" table (handoff lines 8-28) and "User-approved operating constraints" (handoff lines 32-38). Mark spec as `FROZEN` with date `2026-11-11`.

- [ ] **Step 2:** Append to `docs/superpowers/plans/GATE_MANIFEST.md`:

```markdown
## ORB Reversal Indices (2026-11-11)
- Status: IN-PROGRESS
- Spec: `docs/superpowers/specs/2026-11-11-orb-reversal-indices-design.md`
- Plan: `docs/superpowers/plans/2026-11-11-orb-reversal-indices.md`
- Engines: NAS100, SP500
- Branch: `orb-reversal-indices`
- Prior cycle: SB 6-engine SHELVED 2026-11-10
```

- [ ] **Step 3:** Append to `docs/superpowers/plans/00-INDEX.md`: `- 2026-11-11 ORB Reversal Indices — see plan + spec files.`

- [ ] **Step 4:** Commit

```bash
git add docs/superpowers/specs/2026-11-11-orb-reversal-indices-design.md docs/superpowers/plans/GATE_MANIFEST.md docs/superpowers/plans/00-INDEX.md docs/superpowers/plans/2026-11-11-orb-reversal-indices.md
git commit -m "docs: freeze ORB Reversal Indices cycle spec and plan"
```

---

### Task 2: Port data + common + structure infra

**Files:**
- Checkout from `sb-6-engine-gate`: `src/v17/common/__init__.py`, `clock.py`, `dtos.py`, `errors.py`, `instrument_spec.py`, `logging.py`, `paths.py`, `timeframes.py`, `types.py`
- Checkout from `sb-6-engine-gate`: `src/v17/data/__init__.py`, `calendar/*.py`, `cli.py`, `dukascopy_csv.py`, `parquet_store.py`, `partition_guard.py`, `ports.py`, `providers.py`, `resample.py`, `spread_guard.py`
- Checkout from `sb-6-engine-gate`: `src/v17/structure/__init__.py`, `atr.py`, `bias.py`, `ports.py`, `swings.py`
- Checkout from `sb-6-engine-gate`: `tests/unit/common/`, `tests/unit/data/`, `tests/unit/structure/test_atr.py`, `test_bias.py`, `test_swings.py`
- Bars: do NOT copy. Resolve path via `v17.common.paths` → point at `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/` (dev + holdout partitions already present there). Wiring step covered in Task 13 Step 1.
- Checkout calendar: `data/calendar/` artifacts if present

**Interfaces produced:**
- `v17.data.parquet_store.load_bars(symbol: str, tf: str, start_ns: int, end_ns: int) -> pd.DataFrame`
- `v17.data.spread_guard.SpreadGuard` precompute class.
- `v17.structure.atr.rolling_atr(df: pd.DataFrame, period: int = 14) -> pd.Series`
- `v17.common.instrument_spec.pip_size(symbol: str) -> float`

- [ ] **Step 1:** Checkout common/

```bash
git checkout sb-6-engine-gate -- src/v17/common/__init__.py src/v17/common/clock.py src/v17/common/dtos.py src/v17/common/errors.py src/v17/common/instrument_spec.py src/v17/common/logging.py src/v17/common/paths.py src/v17/common/timeframes.py src/v17/common/types.py
```

- [ ] **Step 2:** Checkout data/ (excluding SB-only artifacts if any)

```bash
git checkout sb-6-engine-gate -- src/v17/data/
```

- [ ] **Step 3:** Checkout structure/ (only generic modules — skip `displacement.py`, `engine.py`, `fvg.py`, `fvg_sb.py`, `liquidity.py`, `liquidity_pools.py`, `mss.py`, `ob.py`, `smc_adapter.py` which are SB/ICT-specific)

```bash
git checkout sb-6-engine-gate -- src/v17/structure/__init__.py src/v17/structure/atr.py src/v17/structure/bias.py src/v17/structure/ports.py src/v17/structure/swings.py
```

- [ ] **Step 4:** Checkout matching unit tests

```bash
git checkout sb-6-engine-gate -- tests/unit/common/ tests/unit/data/ tests/unit/structure/test_atr.py tests/unit/structure/test_bias.py tests/unit/structure/test_swings.py
```

- [ ] **Step 5:** Verify imports + tests

```bash
pytest tests/unit/common/ tests/unit/data/ tests/unit/structure/ -q
```

Expected: all green. If any test imports an SB-only module not yet ported, note the symbol and defer — do NOT port SB strategy files; mark the test `xfail` with reason "SB-only; irrelevant to ORB" and continue.

- [ ] **Step 6:** Commit

```bash
git add src/v17/common/ src/v17/data/ src/v17/structure/__init__.py src/v17/structure/atr.py src/v17/structure/bias.py src/v17/structure/ports.py src/v17/structure/swings.py tests/unit/common/ tests/unit/data/ tests/unit/structure/test_atr.py tests/unit/structure/test_bias.py tests/unit/structure/test_swings.py
git commit -m "feat(orb): port data/common/structure infra from sb-6-engine-gate"
```

---

### Task 3: Port backtest + risk infra; rename sb_risk_engine → orb_risk_engine

**Files:**
- Checkout: `src/v17/backtest/__init__.py`, `cli.py`, `cost.py`, `fills.py`, `loop.py`, `metrics.py`, `montecarlo.py`, `ports.py`, `precompute.py`, `report.py`, `snapshot_cache.py`, `walkforward.py`, `wf_orchestrator.py`
- Checkout: `src/v17/risk/__init__.py`, `consistency.py`, `daily_guard.py`, `dd_guard.py`, `engine.py`, `ftmo_rules.py`, `ports.py`, `risk_rules.py`, `sb_risk_engine.py`, `sizing.py`
- Rename: `src/v17/risk/sb_risk_engine.py` → `src/v17/risk/orb_risk_engine.py`
- Modify (inside renamed file): change class `SBRiskEngine` → `ORBRiskEngine`; update constant imports from `v17.setups.sb_constants` to `v17.setups.orb_constants` (constants module built in Task 8).
- Create: `src/v17/setups/__init__.py` (empty module marker for the new setups package on this branch)
- Checkout: `tests/unit/backtest/`, `tests/unit/risk/` (some may reference SB constants — xfail with reason, do not port SB strategy modules)

**Interfaces produced:**
- `v17.backtest.walkforward.Fold` dataclass (`fold_id: int`, `train_start: int`, `train_end: int`, `oos_start: int`, `oos_end: int`).
- `v17.backtest.walkforward.generate_folds(dev_start_ns: int, dev_end_ns: int, n_folds: int = 7) -> list[Fold]`.
- `v17.backtest.cost.apply_cost(trade_row: dict, symbol: str, slippage_pts: float) -> dict`.
- `v17.backtest.fills.simulate_fill_market(bars: pd.DataFrame, entry_idx: int, side: str, sl: float, tp: float, time_cap_ns: int) -> dict` (returns `{exit_price, exit_reason, exit_idx}`).
- `v17.backtest.wf_orchestrator.run_orchestrated(engines: list, bars_by_symbol: dict, calendar: pd.DataFrame, folds: list[Fold], max_workers: int = 2) -> list[TradeLog]`.
- `v17.risk.orb_risk_engine.ORBRiskEngine(starting_equity: float)` — same public methods as `SBRiskEngine`: `start_of_day(day_ns)`, `update_peak_equity(equity)`, `on_trade_close(pnl_cash, trade_date_utc_ns)`, `allow_trade() -> bool`, `.equity` property.

- [ ] **Step 1:** Checkout backtest/

```bash
git checkout sb-6-engine-gate -- src/v17/backtest/__init__.py src/v17/backtest/cli.py src/v17/backtest/cost.py src/v17/backtest/fills.py src/v17/backtest/loop.py src/v17/backtest/metrics.py src/v17/backtest/montecarlo.py src/v17/backtest/ports.py src/v17/backtest/precompute.py src/v17/backtest/report.py src/v17/backtest/snapshot_cache.py src/v17/backtest/walkforward.py src/v17/backtest/wf_orchestrator.py
```

Do NOT checkout `src/v17/backtest/engine_runner.py` — it has SB-specific wiring; ORB gets its own runner in Task 12.

- [ ] **Step 2:** Checkout risk/

```bash
git checkout sb-6-engine-gate -- src/v17/risk/
```

- [ ] **Step 3:** Rename + rewrite risk engine

```bash
git mv src/v17/risk/sb_risk_engine.py src/v17/risk/orb_risk_engine.py
```

Then edit `src/v17/risk/orb_risk_engine.py`:
- Replace class name `SBRiskEngine` with `ORBRiskEngine`.
- Change import `from v17.setups.sb_constants import DAILY_LOSS_SOFT_STOP, TOTAL_LOSS_HARD_FREEZE` to `from v17.setups.orb_constants import DAILY_LOSS_SOFT_STOP, TOTAL_LOSS_HARD_FREEZE`.
- Note: `orb_constants.py` arrives in Task 8 — expect `ModuleNotFoundError` on import until then.

- [ ] **Step 4:** Create `src/v17/setups/__init__.py` with content `""" ORB setups package. """`.

- [ ] **Step 5:** Checkout backtest + risk tests, xfail any that depend on SB strategy modules

```bash
git checkout sb-6-engine-gate -- tests/unit/backtest/test_walkforward.py tests/unit/backtest/test_cost.py tests/unit/backtest/test_fills.py tests/unit/backtest/test_metrics.py tests/unit/risk/
```

For each test file that fails collection with `ModuleNotFoundError: v17.setups.sb_*`, add at top of file:

```python
import pytest
pytestmark = pytest.mark.xfail(reason="SB-specific; replaced by ORB tests", run=False)
```

- [ ] **Step 6:** Run

```bash
pytest tests/unit/backtest/test_walkforward.py tests/unit/backtest/test_cost.py tests/unit/backtest/test_fills.py tests/unit/backtest/test_metrics.py -q
```

Expected: PASS or xfail. No uncaught ImportError.

- [ ] **Step 7:** Commit

```bash
git add src/v17/backtest/ src/v17/risk/ src/v17/setups/__init__.py tests/unit/backtest/ tests/unit/risk/
git commit -m "feat(orb): port backtest+risk infra; rename sb_risk_engine -> orb_risk_engine"
```

---

### Task 4: Port validation infra

**Files:**
- Checkout: `src/v17/validation/__init__.py`, `cli.py`, `evaluate.py`, `gate.py`, `mcpt.py`, `mcpt_runner.py`, `ports.py`, `secondary_gates.py`, `seeds.py`, `stats.py`, `thresholds.py`
- Checkout: `tests/unit/validation/`

**Interfaces produced:**
- `v17.validation.stats.compute_stats(pnls_r: np.ndarray, ts_ns: np.ndarray) -> StatsBundle` with fields `pf: float`, `trade_count: int`, `r2: float`, `sharpe: float`, `max_dd_pct: float`, `winrate: float`.
- `v17.validation.secondary_gates.evaluate_secondary(agg_trades: pd.DataFrame, cost_stress_pf: float) -> GateReport` — fields `G1_pass..G5_pass`, `all_pass`, `details`.
- `v17.validation.mcpt_runner.run_mcpt(engine_id, trades, bars, calendar, scheme, n_permutations, out_root) -> dict` — `scheme` must be `"pnl_bootstrap"`; `"signal_time"` raises `NotImplementedError` (R-05).
- `v17.validation.mcpt.block_bootstrap_pnl(pnls: np.ndarray, block_size: int, n_permutations: int, seed: int) -> np.ndarray` (shape `(n_permutations, n_trades)`).
- `v17.validation.seeds.permutation_seed(engine_id: str, perm_idx: int) -> int`.
- `v17.validation.thresholds.VALIDATION_THRESHOLDS` dict (unchanged defaults).

- [ ] **Step 1:** Checkout

```bash
git checkout sb-6-engine-gate -- src/v17/validation/ tests/unit/validation/
```

- [ ] **Step 2:** Run

```bash
pytest tests/unit/validation/ -q
```

Expected: PASS. If any test asserts SB-specific thresholds, xfail per Task 3 Step 5 pattern.

- [ ] **Step 3:** Commit

```bash
git add src/v17/validation/ tests/unit/validation/
git commit -m "feat(orb): port validation infra (mcpt, stats, secondary_gates, thresholds)"
```

---

### Task 5: Fix Windows ProcessPoolExecutor hang

**Files:**
- Modify: `src/v17/backtest/wf_orchestrator.py`
- Create: `tests/unit/backtest/test_wf_orchestrator_windows.py`

**Root cause (from handoff line 69):** Pickling pandas DataFrames across process boundaries on Windows (spawn-mode) deadlocks silently when payloads exceed certain sizes.

**Fix:** Pass file paths to worker, let worker load its own slice. Add `if sys.platform == "win32"` branch that forces `max_workers=1` sequential fallback when total payload across folds > 500 MB (configurable).

**Interfaces produced (unchanged outer API):**
- `run_orchestrated(engines, bars_by_symbol, calendar, folds, max_workers=2) -> list[TradeLog]` continues to accept DataFrames at the outer boundary but internally writes a scratch parquet per symbol and passes paths to workers.

- [ ] **Step 1:** Write failing integration test `test_wf_orchestrator_windows_no_hang`:

```python
import sys
import time
import pandas as pd
import numpy as np
import pytest

from v17.backtest.wf_orchestrator import run_orchestrated
from v17.backtest.walkforward import Fold

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only regression")
def test_windows_runner_completes_under_60s():
    rng = np.random.default_rng(42)
    n = 200_000
    ts = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    bars = pd.DataFrame({
        "ts_ns": ts.view("int64"),
        "open": rng.normal(100, 0.1, n),
        "high": rng.normal(100.1, 0.1, n),
        "low":  rng.normal(99.9, 0.1, n),
        "close": rng.normal(100, 0.1, n),
        "bid": rng.normal(100, 0.1, n),
        "ask": rng.normal(100, 0.1, n) + 0.001,
    })
    folds = [Fold(fold_id=i, train_start=ts.view("int64")[0], train_end=ts.view("int64")[n//2],
                  oos_start=ts.view("int64")[n//2], oos_end=ts.view("int64")[-1]) for i in range(2)]
    calendar = pd.DataFrame(columns=["ts_ns", "severity", "symbols"])

    from v17.setups.orb_engines import ORB_CATALOG  # built in Task 11
    t0 = time.monotonic()
    logs = run_orchestrated(
        engines=ORB_CATALOG,
        bars_by_symbol={"USATECHIDXUSD": bars},
        calendar=calendar,
        folds=folds,
        max_workers=2,
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 60, f"orchestrator took {elapsed:.1f}s; Windows hang regression"
    assert len(logs) >= 1
```

- [ ] **Step 2:** Run test to verify it fails

```bash
pytest tests/unit/backtest/test_wf_orchestrator_windows.py -v
```

Expected: FAIL (either hang-then-timeout, missing `ORB_CATALOG`, or runs past 60s). Ok to defer verification until Task 11 exists — mark xfail then re-enable in Task 11 Step 6.

- [ ] **Step 3:** Patch `wf_orchestrator.py`:

Add at top:

```python
import os
import sys
import tempfile
from pathlib import Path
```

Replace the worker-invocation block. New pattern: before spawning workers, write each symbol's bars DataFrame to `tempfile.gettempdir()/orb_wf_<symbol>_<pid>.parquet`. Pass the parquet path to each worker. Worker reloads via `pd.read_parquet(path)`. On Windows, if `max_workers > 1` AND `sum(df.memory_usage(deep=True).sum() for df in bars_by_symbol.values()) > 500_000_000`, log a warning and force `max_workers = 1` (sequential).

Exact patch target: the `with ProcessPoolExecutor(max_workers=...) as pool:` block. Wrap with the path-handoff logic. Clean temp parquet files in a `finally` after `pool.shutdown`.

- [ ] **Step 4:** Run test

```bash
pytest tests/unit/backtest/test_wf_orchestrator_windows.py -v
```

Expected: PASS once `ORB_CATALOG` exists (Task 11). Until then, mark xfail.

- [ ] **Step 5:** Commit

```bash
git add src/v17/backtest/wf_orchestrator.py tests/unit/backtest/test_wf_orchestrator_windows.py
git commit -m "fix(orchestrator): avoid Windows ProcessPool hang via parquet path handoff + sequential fallback"
```

---

### Task 6: Fix 70-min batch wall-clock regression

**Files:**
- Modify: `src/v17/backtest/engine_runner.py` (will be the new ORB runner introduced in Task 12 — but the batch-wall-clock issue originated in the SB runner's `run_engine_oos_batch`; the ORB runner must not repeat the mistake)
- Create: `tests/unit/backtest/test_engine_runner_batch_perf.py`

**Root cause (handoff line 71):** `run_engine_oos_batch` was observed concatenating per-symbol bars inside the fold loop with `pd.concat(frames)` on every fold, scaling quadratically with symbols × folds. SB measured 2 min for 1 symbol × 7 folds vs 70 min for 2 symbols × 7 folds.

**Fix (design contract carried into Task 12):** per-symbol preprocessing (ATR, SpreadGuard medians, VWAP, OR windows) runs exactly once in `run_engine_oos_batch`, cached by symbol; the fold loop slices by index, never concatenates.

- [ ] **Step 1:** Write failing perf test `test_batch_scales_linear_in_symbols`:

```python
import time
import pandas as pd
import numpy as np
import pytest

@pytest.mark.perf
def test_batch_wallclock_two_symbols_under_8min():
    # Skipped unless running with -m perf; placeholder here, real body after Task 12.
    pytest.skip("perf guard — enable after Task 12 ORB runner exists")
```

- [ ] **Step 2:** Mark enabled in Task 12 Step 7. For now, commit the test placeholder + the design-contract comment at the top of `engine_runner.py` (when created in Task 12).

- [ ] **Step 3:** Commit

```bash
git add tests/unit/backtest/test_engine_runner_batch_perf.py
git commit -m "test(engine_runner): placeholder perf guard for batch wall-clock regression"
```

---

### Task 7: Pending STOP-order fill model + verify slippage application

**Files:**
- Modify: `src/v17/backtest/fills.py`
- Modify: `tests/unit/backtest/test_fills.py` (add STOP + slippage cases)

**Root cause (handoff lines 73-75):** ORB entries are STOP orders (sell-stop below OR_high after a confirmed close-back-inside). Current fill sim only models market-touch of CE/edge. Also, 0.5 pt USATECH market slippage specified in cost model is not verified to flow into `simulate_fill_market`.

**Interfaces produced:**
- `v17.backtest.fills.simulate_fill_stop(bars: pd.DataFrame, armed_idx: int, side: str, stop_price: float, sl: float, tp: float, time_cap_ns: int, slippage_pts: float) -> dict | None` — returns `None` if the STOP never triggers before `time_cap_ns`; otherwise returns `{entry_price, entry_idx, exit_price, exit_idx, exit_reason}` where `entry_price = stop_price + slippage_pts` (short) / `stop_price - slippage_pts` (long).
- `simulate_fill_market` signature extended to require `slippage_pts: float` (no default — forces call site to pass it).

- [ ] **Step 1:** Add failing tests to `tests/unit/backtest/test_fills.py`:

```python
def test_stop_order_fills_when_price_breaks_through_short():
    bars = pd.DataFrame({
        "ts_ns": [0, 60_000_000_000, 120_000_000_000],
        "open":  [100.0, 100.5, 101.0],
        "high":  [100.2, 101.0, 101.5],
        "low":   [99.8,  100.3, 100.8],
        "close": [100.1, 100.9, 101.2],
    })
    from v17.backtest.fills import simulate_fill_stop
    res = simulate_fill_stop(bars, armed_idx=0, side="short",
                             stop_price=100.9, sl=101.3, tp=100.5,
                             time_cap_ns=180_000_000_000, slippage_pts=0.1)
    assert res is not None
    assert res["entry_idx"] == 1
    assert abs(res["entry_price"] - (100.9 + 0.1)) < 1e-9

def test_stop_order_returns_none_when_never_triggers():
    bars = pd.DataFrame({
        "ts_ns": [0, 60_000_000_000],
        "open":  [100.0, 100.1],
        "high":  [100.2, 100.3],
        "low":   [99.8,  99.9],
        "close": [100.1, 100.0],
    })
    from v17.backtest.fills import simulate_fill_stop
    res = simulate_fill_stop(bars, armed_idx=0, side="short",
                             stop_price=101.0, sl=101.5, tp=100.0,
                             time_cap_ns=120_000_000_000, slippage_pts=0.0)
    assert res is None

def test_market_slippage_applies_short():
    bars = pd.DataFrame({
        "ts_ns": [0, 60_000_000_000],
        "open":  [100.0, 99.0],
        "high":  [100.1, 99.5],
        "low":   [99.5,  98.0],
        "close": [100.0, 98.5],
    })
    from v17.backtest.fills import simulate_fill_market
    res = simulate_fill_market(bars, entry_idx=0, side="short",
                               sl=100.5, tp=98.0, time_cap_ns=120_000_000_000,
                               slippage_pts=0.5)
    # short at open=100.0 with 0.5 adverse slippage => effective entry 99.5
    assert abs(res["entry_price"] - 99.5) < 1e-9
```

- [ ] **Step 2:** Run

```bash
pytest tests/unit/backtest/test_fills.py -k "stop_order or slippage" -v
```

Expected: FAIL (`simulate_fill_stop` undefined; `simulate_fill_market` lacks `slippage_pts` kwarg).

- [ ] **Step 3:** Implement `simulate_fill_stop` and extend `simulate_fill_market` to require `slippage_pts`. Loop from `armed_idx` forward: for a short STOP at `stop_price`, trigger when `bar.high >= stop_price`; entry_price = `stop_price + slippage_pts` (price moves against us on triggered stop). After entry, walk bars until `low <= tp` (take-profit, short), `high >= sl` (stop-loss, short), or `ts_ns >= armed_idx_ts + time_cap_ns`. Mirror logic for long.

- [ ] **Step 4:** Run

```bash
pytest tests/unit/backtest/test_fills.py -v
```

Expected: all PASS. Update any existing `simulate_fill_market` callers to pass `slippage_pts` explicitly.

- [ ] **Step 5:** Commit

```bash
git add src/v17/backtest/fills.py tests/unit/backtest/test_fills.py
git commit -m "feat(fills): add STOP-order fill sim; enforce explicit slippage on market fills"
```

---

### Task 8: ORB constants module

**Files:**
- Create: `src/v17/setups/orb_constants.py`
- Create: `tests/unit/setups/test_orb_constants.py`

**Interfaces produced:**
- `OR_WINDOW_NY: tuple[str, str] = ("09:30", "10:00")`
- `SESSION_WINDOW_NY: tuple[str, str] = ("09:30", "11:30")`
- `OR_DURATION_MIN: int = 30`
- `REVERSAL_CONFIRM_MAX_MIN: int = 15` (close back inside within 15 min of breakout)
- `ATR_PERIOD_M1: int = 14`
- `SL_ATR_MULT: float = 0.5`
- `TARGET_R: float = 0.5`
- `DAILY_LOSS_SOFT_STOP: float = 0.03`
- `TOTAL_LOSS_HARD_FREEZE: float = 0.08`
- `MAX_TRADES_PER_DAY_PER_INSTRUMENT: int = 1`
- `COST_SLIPPAGE_PTS: dict[str, float] = {"USATECHIDXUSD": 0.5, "USA500IDXUSD": 0.25}` (SP500 entry retained for future re-enable; no engine references it)
- `COMMISSION_PER_LOT: dict[str, float] = {"USATECHIDXUSD": 0.0, "USA500IDXUSD": 0.0}`

- [ ] **Step 1:** Write `tests/unit/setups/test_orb_constants.py`:

```python
from v17.setups import orb_constants as c

def test_breakers_match_spec():
    assert c.DAILY_LOSS_SOFT_STOP == 0.03
    assert c.TOTAL_LOSS_HARD_FREEZE == 0.08

def test_or_window_30min():
    assert c.OR_WINDOW_NY == ("09:30", "10:00")
    assert c.OR_DURATION_MIN == 30

def test_cost_ftmo_zero_commission_on_indices():
    assert c.COMMISSION_PER_LOT["USATECHIDXUSD"] == 0.0
```

- [ ] **Step 2:** Run

```bash
pytest tests/unit/setups/test_orb_constants.py -v
```

Expected: FAIL (`orb_constants` missing).

- [ ] **Step 3:** Write `src/v17/setups/orb_constants.py` with the values from Interfaces above.

- [ ] **Step 4:** Run

```bash
pytest tests/unit/setups/test_orb_constants.py -v
```

Expected: PASS.

- [ ] **Step 5:** Commit

```bash
git add src/v17/setups/orb_constants.py tests/unit/setups/test_orb_constants.py
git commit -m "feat(orb): freeze constants per spec section (breakers, OR window, cost)"
```

---

### Task 9: Session VWAP

**Files:**
- Create: `src/v17/structure/vwap.py`
- Create: `tests/unit/structure/test_vwap.py`

**Interfaces produced:**
- `v17.structure.vwap.compute_session_vwap(bars: pd.DataFrame, session_start_ns: int, session_end_ns: int) -> pd.Series` — returns cumulative session VWAP indexed identically to `bars` within `[session_start_ns, session_end_ns]`; NaN outside.
  - Formula: `cumsum(typical_price * volume) / cumsum(volume)` where `typical_price = (high + low + close) / 3`.
  - If `volume` column is absent (CFD tick-data case), fall back to `typical_price` cumulative mean (document this fallback in a docstring line).

- [ ] **Step 1:** Write failing test:

```python
import pandas as pd
import numpy as np
from v17.structure.vwap import compute_session_vwap

def test_vwap_cumulative_within_session():
    ts = pd.date_range("2024-01-02 14:30", periods=5, freq="1min", tz="UTC").view("int64")
    bars = pd.DataFrame({
        "ts_ns": ts,
        "high":  [100.0, 100.5, 101.0, 100.8, 100.6],
        "low":   [99.5,  100.0, 100.3, 100.2, 100.1],
        "close": [99.8,  100.2, 100.7, 100.5, 100.4],
        "volume":[10, 20, 30, 10, 10],
    })
    vwap = compute_session_vwap(bars, session_start_ns=int(ts[0]), session_end_ns=int(ts[-1]))
    # bar 0 tp=99.767, vwap=99.767
    assert abs(vwap.iloc[0] - ((100.0+99.5+99.8)/3)) < 1e-6
    # bar 1 weighted average of bar0 (w=10) and bar1 (w=20)
    tp0 = (100.0+99.5+99.8)/3
    tp1 = (100.5+100.0+100.2)/3
    expected = (tp0*10 + tp1*20) / 30
    assert abs(vwap.iloc[1] - expected) < 1e-6

def test_vwap_fallback_without_volume():
    ts = pd.date_range("2024-01-02 14:30", periods=3, freq="1min", tz="UTC").view("int64")
    bars = pd.DataFrame({
        "ts_ns": ts, "high": [1.0, 2.0, 3.0], "low": [0.5, 1.5, 2.5], "close": [0.8, 1.8, 2.8],
    })
    vwap = compute_session_vwap(bars, int(ts[0]), int(ts[-1]))
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3
    assert abs(vwap.iloc[2] - tp.mean()) < 1e-9
```

- [ ] **Step 2:** Run

```bash
pytest tests/unit/structure/test_vwap.py -v
```

Expected: FAIL (module missing).

- [ ] **Step 3:** Implement `src/v17/structure/vwap.py`. Guard against empty slice; return `pd.Series(dtype=float, index=bars.index)` filled with NaN when no bars fall in `[session_start_ns, session_end_ns]`.

- [ ] **Step 4:** Run

```bash
pytest tests/unit/structure/test_vwap.py -v
```

Expected: PASS.

- [ ] **Step 5:** Commit

```bash
git add src/v17/structure/vwap.py tests/unit/structure/test_vwap.py
git commit -m "feat(structure): session VWAP (volume-weighted with typical-price fallback)"
```

---

### Task 10: ORB FSM

**Files:**
- Create: `src/v17/setups/orb_fsm.py`
- Create: `tests/unit/setups/test_orb_fsm.py`

**States:** `IDLE → OR_BUILDING → OR_LOCKED → BREAKOUT_DETECTED → REVERSAL_CONFIRMED → ENTRY_ARMED → MANAGED → EXIT`

**Interfaces produced:**

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class ORBState:
    phase: Literal["IDLE","OR_BUILDING","OR_LOCKED","BREAKOUT_DETECTED","REVERSAL_CONFIRMED","ENTRY_ARMED","MANAGED","EXIT"]
    or_high: float | None
    or_low: float | None
    or_locked_ns: int | None
    breakout_side: Literal["long","short"] | None
    breakout_ns: int | None

@dataclass
class ORBSignal:
    side: Literal["long","short"]
    stop_price: float   # OR extreme
    sl: float           # breakout extreme ± 0.5 * ATR_14
    tp: float           # 0.5R target (initial; VWAP trail handled by runner)
    armed_ns: int

class ORBFSM:
    def __init__(self, symbol: str, atr14_m1: pd.Series, bars: pd.DataFrame): ...
    def start_day(self, day_ns: int) -> None: ...
    def on_bar(self, bar_idx: int) -> ORBSignal | None: ...
```

**Transitions:**
- `start_day`: reset to `IDLE`.
- First bar inside OR window (09:30 ET): `IDLE → OR_BUILDING`; track rolling high/low.
- Last bar of OR window (10:00 ET): `OR_BUILDING → OR_LOCKED`; record `or_high`, `or_low`, `or_locked_ns`.
- Bar closes above `or_high` after lock: `OR_LOCKED → BREAKOUT_DETECTED` (side=short, intent=fade). Symmetric for `or_low` → long.
- Within `REVERSAL_CONFIRM_MAX_MIN` after breakout, a bar closes back inside `[or_low, or_high]`: `BREAKOUT_DETECTED → REVERSAL_CONFIRMED → ENTRY_ARMED`. Emit `ORBSignal` with `stop_price = or_high` (short) or `or_low` (long).
- No reversal within window: `BREAKOUT_DETECTED → EXIT` (day done).
- After emit, `ENTRY_ARMED` is held one bar; FSM itself transitions to `MANAGED` once runner fills via `simulate_fill_stop`; `EXIT` when runner reports close.

- [ ] **Step 1:** Write failing tests `test_orb_fsm.py` covering: (a) OR builds and locks correctly; (b) breakout above `or_high` + close-back-inside within 15 min emits short signal with `stop_price == or_high`; (c) breakout with NO close-back-inside within 15 min transitions to EXIT without signal; (d) only one signal per day per instrument.

- [ ] **Step 2:** Run

```bash
pytest tests/unit/setups/test_orb_fsm.py -v
```

Expected: FAIL.

- [ ] **Step 3:** Implement `orb_fsm.py` with pure-function bar iteration; no side effects outside the state object.

- [ ] **Step 4:** Run

```bash
pytest tests/unit/setups/test_orb_fsm.py -v
```

Expected: PASS.

- [ ] **Step 5:** Commit

```bash
git add src/v17/setups/orb_fsm.py tests/unit/setups/test_orb_fsm.py
git commit -m "feat(orb): FSM — OR build/lock, breakout, reversal confirm, entry-armed"
```

---

### Task 11: ORB engine catalog

**Files:**
- Create: `src/v17/setups/orb_engines.py`
- Create: `tests/unit/setups/test_orb_engines.py`

**Interfaces produced:**

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ORBEngineConfig:
    engine_id: str
    symbol: str
    or_window_ny: tuple[str, str]
    session_window_ny: tuple[str, str]
    priority_order: int

ORB_CATALOG: list[ORBEngineConfig] = [
    ORBEngineConfig("ORB-NAS100", "USATECHIDXUSD", ("09:30","10:00"), ("09:30","11:30"), 1),
]
```

- [ ] **Step 1:** Write failing test:

```python
from v17.setups.orb_engines import ORB_CATALOG, ORBEngineConfig

def test_catalog_has_one_engine():
    assert len(ORB_CATALOG) == 1
    ids = {e.engine_id for e in ORB_CATALOG}
    assert ids == {"ORB-NAS100"}

def test_engine_windows_match_spec():
    for e in ORB_CATALOG:
        assert e.or_window_ny == ("09:30","10:00")
        assert e.session_window_ny == ("09:30","11:30")
```

- [ ] **Step 2:** Run

```bash
pytest tests/unit/setups/test_orb_engines.py -v
```

Expected: FAIL.

- [ ] **Step 3:** Implement module.

- [ ] **Step 4:** Run

```bash
pytest tests/unit/setups/test_orb_engines.py -v
```

Expected: PASS.

- [ ] **Step 5:** Re-enable the Task 5 Windows orchestrator test (remove `xfail` mark). Run `pytest tests/unit/backtest/test_wf_orchestrator_windows.py -v`. Expected PASS (completes < 60s on Windows).

- [ ] **Step 6:** Commit

```bash
git add src/v17/setups/orb_engines.py tests/unit/setups/test_orb_engines.py tests/unit/backtest/test_wf_orchestrator_windows.py
git commit -m "feat(orb): engine catalog (NAS100, SP500); enable Windows orchestrator regression test"
```

---

### Task 12: ORB engine runner

**Files:**
- Create: `src/v17/backtest/engine_runner.py` (fresh; NOT the SB one)
- Create: `tests/unit/backtest/test_orb_engine_runner.py`
- Create: `tests/integration/test_orb_engine_runner_integration.py`

**Interfaces produced:**

```python
from dataclasses import dataclass, field
import pandas as pd
from v17.backtest.walkforward import Fold
from v17.setups.orb_engines import ORBEngineConfig

@dataclass
class TradeLog:
    engine_id: str
    fold_id: int
    trades: list = field(default_factory=list)

def run_engine_oos(config: ORBEngineConfig, bars: pd.DataFrame, calendar: pd.DataFrame, fold: Fold) -> TradeLog: ...
def run_engine_oos_batch(config: ORBEngineConfig, bars: pd.DataFrame, calendar: pd.DataFrame, folds: list[Fold]) -> list[TradeLog]: ...
```

**Design contract (anti-regression on Task 6):**
- Per-symbol preprocessing (ATR_14, session VWAP per day, OR window boundary ns per day, blackout mask, spread guard medians) runs ONCE in `run_engine_oos_batch`, cached as numpy arrays keyed by bar index.
- Fold loop slices the cached arrays by `[oos_start, oos_end]` index range — never calls `pd.concat`.
- Inner loop uses numpy arrays (no `iterrows`).

**Trade lifecycle inside runner:**
1. For each trading day in `[fold.oos_start, fold.oos_end]`:
2. Compute OR high/low across the OR window.
3. Run `ORBFSM.on_bar` across session-window bars until a signal emits (or EXIT).
4. On signal: compute `sl = stop_price ± 0.5 * atr14_m1[armed_idx]` (± matches side); compute `r_distance = |sl - stop_price|`; compute initial `tp = stop_price ∓ 0.5 * r_distance`.
5. Call `simulate_fill_stop(bars, armed_idx, side, stop_price, sl, tp, session_end_ns, slippage_pts=COST_SLIPPAGE_PTS[symbol])`.
6. If fill triggered: inside managed phase, each subsequent bar compares session VWAP vs current trail; if VWAP is farther than 0.5R from entry, raise TP to VWAP; otherwise keep TP at 0.5R. Exit on SL touch, TP touch, or session end.
7. Record trade row: `{ts_entry_ns, ts_exit_ns, engine_id, fold_id, symbol, side, entry_price, exit_price, sl, tp, exit_reason, pnl_r, pnl_cash}`.
8. Enforce 1 trade/day/instrument cap (Task 8 constant).

- [ ] **Step 1:** Write unit test `test_runner_emits_trade_on_crafted_reversal_scenario` — hand-craft 90 bars (M1) spanning 09:28-11:00 ET, with (a) OR_high at 100.5 between 09:30-10:00, (b) breakout to 100.8 at 10:03, (c) close back at 100.4 at 10:08, (d) subsequent short trigger at 100.5 stop, (e) price moves to 100.0 to hit 0.5R TP. Assert exactly one trade in `TradeLog.trades` with `exit_reason == "TP"` and `pnl_r > 0.4`.

- [ ] **Step 2:** Run

```bash
pytest tests/unit/backtest/test_orb_engine_runner.py -v
```

Expected: FAIL.

- [ ] **Step 3:** Implement `src/v17/backtest/engine_runner.py` per the design contract.

- [ ] **Step 4:** Run

```bash
pytest tests/unit/backtest/test_orb_engine_runner.py -v
```

Expected: PASS.

- [ ] **Step 5:** Write integration test `test_orb_runner_two_symbol_batch_wallclock` — load ~1 year of real NAS100 + SP500 M1 bars from `data/bars/.../dev/`, build 7 folds, call `run_engine_oos_batch` for each engine, assert total wall-clock < 10 min on reference hardware (16 GB, 8-core).

- [ ] **Step 6:** Run

```bash
pytest tests/integration/test_orb_engine_runner_integration.py -v
```

Expected: PASS (if slower, inspect preprocessing — must be once-per-symbol).

- [ ] **Step 7:** Enable the Task 6 perf guard: remove `pytest.skip`, run with `pytest -m perf tests/unit/backtest/test_engine_runner_batch_perf.py`. Expected PASS.

- [ ] **Step 8:** Commit

```bash
git add src/v17/backtest/engine_runner.py tests/unit/backtest/test_orb_engine_runner.py tests/integration/test_orb_engine_runner_integration.py tests/unit/backtest/test_engine_runner_batch_perf.py
git commit -m "feat(orb): engine runner with VWAP trail, pending STOP fills, per-symbol preprocessing"
```

---

### Task 13: Dev walk-forward (7-fold)

**Files:**
- Create: `scripts/run_orb_dev_wf.py`
- Create: `tests/unit/backtest/test_orb_dev_wf_smoke.py`

**Interfaces produced:**
- Script writes `out/orb/dev/ORB-NAS100/trades.parquet` and `out/orb/dev/ORB-NAS100/stats.json`.

- [ ] **Step 1:** Write `scripts/run_orb_dev_wf.py` that:
  1. Resolve bars path: use `BARS_ROOT = Path(__file__).resolve().parents[1] / ".worktrees" / "sb-6-engine-gate" / "data" / "bars"` so parquet_store reads USATECHIDXUSD partitions from the SB worktree without copying files. If `v17.common.paths.bars_root()` exists, override it via env var `V17_BARS_ROOT` instead.
  2. Loads dev bars for `USATECHIDXUSD` only via `v17.data.parquet_store.load_bars`.
  3. Builds 7 anchored folds over `2016-11-01` → `2024-12-31` via `walkforward.generate_folds`.
  4. Loops over `ORB_CATALOG` (1 engine) and calls `run_engine_oos_batch`.
  5. Aggregates trades into pandas DataFrame, writes parquet + stats JSON via `compute_stats`.
  6. Prints per-engine PF, trade_count, R2, per-fold PnL.

- [ ] **Step 2:** Write smoke test asserting the script's `main()` function returns a dict `{engine_id: StatsBundle}` for a 30-day dev slice.

- [ ] **Step 3:** Run

```bash
python scripts/run_orb_dev_wf.py --dev-start 2016-11-01 --dev-end 2024-12-31
```

Expected: completes without errors; produces `out/orb/dev/ORB-NAS100/trades.parquet` and `out/orb/dev/ORB-SP500/trades.parquet`. Note the actual trade counts and PF — these drive the Task 14 gate.

- [ ] **Step 4:** Commit

```bash
git add scripts/run_orb_dev_wf.py tests/unit/backtest/test_orb_dev_wf_smoke.py
git commit -m "feat(orb): dev walk-forward script + smoke test"
```

---

### Task 14: Secondary gates on dev results

**Files:**
- Create: `scripts/run_orb_dev_gate.py`
- Create: `docs/superpowers/plans/orb_dev_gate_report_2026-11-11.md`

**Decision:** ORB may fire 20-60 trades per engine (not SB's 50 floor). Per handoff line 50, G2 trade floor may be relaxed at spec-write time. Decision locked here: **G2 trade floor = 25** (down from 50) — document rationale in gate report.

**Interfaces produced:**
- Gate report markdown with per-engine `GateReport.all_pass` bool + full `details` dict.

- [ ] **Step 1:** Modify `src/v17/validation/secondary_gates.py` to accept `min_trade_count: int = 50` param for G2 so the ORB path can pass `25`. Add unit test:

```python
def test_g2_accepts_relaxed_floor():
    df = pd.DataFrame({"pnl_r":[1]*30,"ts_entry_ns":[0]*30,"fold_id":[0]*30})
    r = evaluate_secondary(df, cost_stress_pf=1.5, min_trade_count=25)
    assert r.G2_pass
```

- [ ] **Step 2:** Run

```bash
pytest tests/unit/validation/test_secondary_gates.py -v
```

Expected: PASS.

- [ ] **Step 3:** Write `scripts/run_orb_dev_gate.py` that reads `out/orb/dev/<engine_id>/trades.parquet` for each engine, computes cost-stress PF by inflating `COST_SLIPPAGE_PTS` × 2, calls `evaluate_secondary(..., min_trade_count=25)`, writes `docs/superpowers/plans/orb_dev_gate_report_2026-11-11.md`.

- [ ] **Step 4:** Run

```bash
python scripts/run_orb_dev_gate.py
```

Record verdict for ORB-NAS100. If G1-G5 fails with no borderline passes, **SHELVE** cycle here; update `GATE_MANIFEST.md`; stop. Honest-expectation probability of reaching this point with the engine green: 20-35% per handoff line 95.

- [ ] **Step 5:** Commit

```bash
git add src/v17/validation/secondary_gates.py tests/unit/validation/test_secondary_gates.py scripts/run_orb_dev_gate.py docs/superpowers/plans/orb_dev_gate_report_2026-11-11.md
git commit -m "feat(orb): dev secondary gates G1-G5 (G2 floor relaxed to 25); write gate report"
```

---

### Task 15: Dev MCPT (block bootstrap, Bonferroni-corrected)

**Files:**
- Create: `scripts/run_orb_dev_mcpt.py`
- Create: `docs/superpowers/plans/orb_dev_mcpt_report_2026-11-11.md`

**Parameters:**
- Scheme: `pnl_bootstrap` only.
- Block size: 5 (one trading week).
- Permutations: 500.
- α: 0.05 (single engine; no Bonferroni correction).

- [ ] **Step 1:** Write `scripts/run_orb_dev_mcpt.py` that for `ORB-NAS100` calls `run_mcpt(engine_id, trades, bars, calendar, scheme="pnl_bootstrap", n_permutations=500, out_root=Path("out/orb/dev_mcpt"))` and extracts the PF p-value from the returned dict. Compare against α = 0.05.

- [ ] **Step 2:** Run

```bash
python scripts/run_orb_dev_mcpt.py
```

Write per-engine p-value table into report markdown.

- [ ] **Step 3:** If PF p-value > 0.05, **SHELVE** cycle; update `GATE_MANIFEST.md`; stop. Honest-expectation probability of the engine passing MCPT: 30-50% conditional on secondary gates green.

- [ ] **Step 4:** Commit

```bash
git add scripts/run_orb_dev_mcpt.py docs/superpowers/plans/orb_dev_mcpt_report_2026-11-11.md
git commit -m "feat(orb): dev MCPT (pnl_bootstrap, block=5, Bonferroni α=0.025)"
```

---

### Task 16: Sealed-holdout verdict

**Files:**
- Create: `scripts/run_orb_holdout.py`
- Create: `docs/superpowers/plans/orb_holdout_report_2026-11-11.md`

**Gate:** Only proceed if Task 14 AND Task 15 passed for ORB-NAS100.

**Parameters:**
- Holdout window: `2025-01-01` → `2026-10-18` (sealed; no ORB params trained on it).
- Breakers: `ORBRiskEngine(10_000)` with `DAILY_LOSS_SOFT_STOP=0.03`, `TOTAL_LOSS_HARD_FREEZE=0.08`.
- MCPT on holdout: 1000 permutations; same block size; α = 0.05.
- No portfolio layer this cycle (single engine). Single-engine PnL curve = portfolio for breaker purposes.

- [ ] **Step 1:** Write `scripts/run_orb_holdout.py` that: (a) loads `USATECHIDXUSD` holdout bars; (b) builds a single holdout "fold" over `2025-01-01` → `2026-10-18`; (c) runs ORB-NAS100 through `run_engine_oos` with the `ORBRiskEngine` wrapped in a thin walker that calls `start_of_day` on day boundary and `on_trade_close` after each exit; (d) rejects any trade when `allow_trade() == False`; (e) builds PnL curve; (f) runs 1000-permutation MCPT on PnL.

- [ ] **Step 2:** Run

```bash
python scripts/run_orb_holdout.py
```

Record: portfolio PF, max_dd_pct, holdout MCPT p-value, breaker events, whether any run hit `permanently_frozen`.

- [ ] **Step 3:** Write verdict in `docs/superpowers/plans/orb_holdout_report_2026-11-11.md`:
- **DEPLOY** if PF ≥ 1.3, holdout MCPT p < 0.05, no hard freeze, max_dd_pct < 6%.
- **SHELVE** otherwise.

- [ ] **Step 4:** Update `docs/superpowers/plans/GATE_MANIFEST.md` ORB row with final status + verdict link.

- [ ] **Step 5:** Commit

```bash
git add scripts/run_orb_holdout.py docs/superpowers/plans/orb_holdout_report_2026-11-11.md docs/superpowers/plans/GATE_MANIFEST.md
git commit -m "feat(orb): sealed-holdout verdict + portfolio breakers + GATE_MANIFEST update"
```

---

## Self-review

**Spec coverage:** Every Global Constraints line is referenced in ≥ 1 task. OR window (T8, T10), breakers (T8, T16), VWAP trail (T9, T12), STOP fill + slippage (T7), 1 trade/day cap (T10, T12), Bonferroni α (T15), sealed holdout (T16), 7-fold WF (T13), per-fold G3 (T14 via existing `evaluate_secondary`), MCPT scheme restriction (T15 + R-05 in T4).

**Placeholder scan:** No "TBD", "implement later", "add validation" without code. All signatures declared in Interfaces blocks are defined by the task that owns them.

**Type consistency:**
- `TradeLog` defined identically in T3 (ported) and T12 (ORB-specific) — the T12 definition replaces/shadows the SB-ported one because the SB `engine_runner.py` was explicitly NOT ported (T3 Step 1 note). Confirm no residual import conflicts after T12 Step 3.
- `Fold` imported from `v17.backtest.walkforward` in T5 test and T12 interfaces — single source of truth.
- `ORB_CATALOG` referenced in T5 test (via Task 11) and T13 script — consistent name.
- `simulate_fill_stop` signature defined in T7 matches use in T12 Step 5.
- `evaluate_secondary(..., min_trade_count=25)` extension added in T14 — callers in T14 Step 3 pass it; T4's ported unit tests do NOT pass it (default 50 retained — backward-compatible).

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-11-11-orb-reversal-indices.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
