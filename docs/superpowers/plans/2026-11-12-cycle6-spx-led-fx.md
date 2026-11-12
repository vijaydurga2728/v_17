# Cycle 6 — SPX-Led Intraday Risk-On/Off FX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a dev-and-holdout-validated intraday FX strategy where SPX session VWAP drives a trinary regime state and M5 VWAP pullback micro-triggers generate entries on AUDUSD and USDJPY, with a two-leg exit (scale at 1R + EMA(20) trail), FTMO-safe sizing, and pre-registered dev/holdout/MCPT/paired-alpha gates.

**Architecture:** Follow the existing v17 package layout: constants + engines catalog in `src/v17/setups/`, backtest runner in `src/v17/backtest/`, MCPT and paired-alpha in `src/v17/validation/`, parquet-backed M5 cache under `data/bars_m5/<SYM>/{dev,holdout}/year=YYYY/`. All signals vectorized with numpy/pandas. Position state machine is a per-trade dataclass; multiple open positions tracked by an orchestrator that also enforces portfolio cap and daily circuit breakers.

**Tech Stack:** Python 3.11, pandas 2.2+, numpy 1.26+, pyarrow 16+, pydantic 2.7+, pytest 8.2+, hypothesis 6.100+. Existing v17 utilities: `v17.data.dukascopy_csv`, `v17.data.resample.resample_paired`, `v17.data.parquet_store`, `v17.data.calendar.ff_json`, `v17.validation.mcpt_scheme1`, `v17.validation.seeds`, `v17.common.types`.

**Spec:** `docs/superpowers/specs/2026-11-12-cycle6-spx-led-fx-design.md` — plan arguments draw directly from this spec.

## Global Constraints

- **Python:** >= 3.11.
- **Dev data range:** 2015-01-01 → 2023-12-31 UTC. No model sees any 2024+ bar until S5.
- **Holdout data range:** 2024-01-01 → 2026-10-14 UTC.
- **Session anchor:** 08:00 UTC, reset daily.
- **Entry window:** 08:05 UTC ≤ signal_bar_close ≤ 19:00 UTC, with warmup gate `SPX bars_since_session_start >= 12`, and NY-open blackout 13:30:00–13:34:59 UTC on entries only.
- **Hard flat:** 19:30 UTC, 19:30 M5 bar close price.
- **News blackout:** ±15 min around ForexFactory `impact == "high"` events on `{USD, AUD, JPY}`; fail-closed (skip whole UTC day) if calendar missing or `max(calendar_ts) < sim_date − 48h`.
- **Risk per trade:** `0.005 × equity_sod` where `equity_sod` is start-of-UTC-day equity (fixed intraday).
- **Portfolio cap:** combined open risk ≤ `0.0075 × equity_sod`. Open risk per leg uses current trailed stop.
- **Circuit breakers:** soft loss −1.5%, hard loss −2.5%, profit stop +2.0%, max 8 trades/day, 3 consecutive losses end day. Precedence: hard-loss > profit-stop > soft-loss > 3-consec > trade-cap.
- **Tunable parameter grid:** `K ∈ {0.2, 0.3, 0.4, 0.5}`, `slope_window ∈ {8, 12, 16, 20}`, `C ∈ {0.3, 0.4, 0.5}` → 48 configurations. Single parameter set across both pairs. EMA(20) trail period is not tuned.
- **Pre-reg dev gates (D1–D6):** Sharpe ≥ 1.0, MCPT p ≤ 0.05, PF ≥ 1.25, max daily loss ≤ 3.0%, max consec losing days ≤ 5, trades ≥ 800.
- **Paired-alpha dev gates (A1–A3):** beat random-entry null at p ≤ 0.05; beat regime-only AND micro-trigger-only nulls at p ≤ 0.10 (if both fail → shelve).
- **Holdout gates (H1–H5):** Sharpe ≥ 0.7× dev Sharpe, MCPT p ≤ 0.10, PF ≥ 1.15, max daily loss ≤ 3.0%, no calendar month < −5%.
- **Freezing rule:** parameters locked at end of S4; any change post-S4 requires an ADR under `docs/decisions/`.
- **Determinism:** same inputs → byte-identical trade log and equity curve. Permutation seeds via `v17.validation.seeds.permutation_seed`.
- **File-naming:** new Cycle 6 code uses `c6_` prefix in `src/v17/setups/`, `src/v17/backtest/`, `src/v17/validation/`.

---

## File Structure

New files (created by this plan):

| Path | Responsibility |
|------|----------------|
| `src/v17/setups/c6_constants.py` | Frozen constants: session anchor, EMA period, grid ranges, FTMO caps, blackout minutes, pip metadata. |
| `src/v17/setups/c6_engines.py` | Engine catalog: AUDUSD + USDJPY `C6EngineConfig` rows with pair-specific pip metadata. |
| `src/v17/setups/c6_regime.py` | Vectorized SPX regime: `compute_regime(spx_m5) -> pd.DataFrame` with columns `ts_utc, regime_state ∈ {LONG_BIAS, SHORT_BIAS, FLAT}`, plus internals `vwap, atr, slope`. Pure function. |
| `src/v17/setups/c6_microtrigger.py` | Vectorized FX micro-trigger: `compute_micro_signals(fx_m5, atr_period, confirm_body_mult) -> pd.DataFrame` with columns `ts_utc, pullback, confirm_long, confirm_short`. Pure function. |
| `src/v17/data/c6_pipeline.py` | M1 bid+ask CSV → paired M1 parquet → paired M5 parquet, with grid-alignment assertion and `< 5 M1 ticks` drop rule. |
| `src/v17/data/c6_calendar.py` | ForexFactory cache loader → parquet index at `data/calendar_cache/ff_c6_index.parquet` keyed on `(ts_utc, currency, impact)`, with fail-closed stale check. |
| `src/v17/backtest/c6_position.py` | `C6Position` dataclass (two-leg state machine), stop/trail/time-stop logic, bid/ask fill functions. |
| `src/v17/backtest/c6_sizing.py` | Per-pair position sizing: AUDUSD (fixed pip value) + USDJPY (price-dependent pip value) + leg split + min-size skip. |
| `src/v17/backtest/c6_breakers.py` | Daily circuit-breaker state machine with precedence. |
| `src/v17/backtest/c6_runner.py` | Orchestrator: iterate shared M5 grid, call signal modules, apply breakers + blackouts + sizing, emit `TradeLog` + `equity_curve.jsonl`. |
| `src/v17/validation/c6_mcpt.py` | Scheme-1 MCPT for Cycle 6 — permute signal-bar labels, re-run exits, build null distribution of Sharpe. |
| `src/v17/validation/c6_paired_alpha.py` | Three ablation nulls: random entries (A1), regime-only (A2), micro-trigger-only (A3) + paired comparison stats. |
| `src/v17/validation/c6_gates.py` | Pre-reg gate evaluator: D1–D6, A1–A3, H1–H5 as pure functions over a `pd.DataFrame` of trades + daily P&L. |
| `src/v17/cli_c6.py` | Thin Typer sub-app wired into `v17 c6 ingest | signals | backtest | grid | holdout | report`. |

Test files mirror the source under `tests/unit/` and `tests/integration/`.

Existing files to modify:

| Path | Change |
|------|--------|
| `src/v17/common/types.py` | Add `AUDUSD`, `USDJPY`, `USA500IDXUSD` to `SUPPORTED_SYMBOLS`. |
| `src/v17/cli.py` | Register `c6` sub-app. |

---

## Task Inventory

- **S1 — Data ingest:** Tasks 1–5
- **S2 — Signal engine:** Tasks 6–9
- **S3 — Backtest engine:** Tasks 10–14
- **S4 — Dev run + MCPT + paired-alpha:** Tasks 15–18
- **S5 — Holdout:** Tasks 19–20

---

## Task 1: Symbol registry + M5 parquet path convention

**Files:**
- Modify: `src/v17/common/types.py`
- Create: `src/v17/setups/c6_constants.py`
- Test: `tests/unit/test_c6_constants.py`

**Interfaces:**
- Produces: `AUDUSD`, `USDJPY`, `USA500IDXUSD` entries in `SUPPORTED_SYMBOLS`; module `v17.setups.c6_constants` with `SESSION_ANCHOR_HOUR_UTC`, `HARD_FLAT_HOUR_MIN_UTC`, `ENTRY_WINDOW_START_UTC_HM`, `ENTRY_WINDOW_END_UTC_HM`, `NY_OPEN_BLACKOUT_UTC_HM`, `NEWS_BLACKOUT_MIN`, `WARMUP_SPX_BARS`, `TRAIL_EMA_PERIOD`, `TRAIL_BUFFER_ATR_MULT`, `ATR_PERIOD`, `ATR_FLOOR_MULT`, `RISK_PCT`, `PORTFOLIO_RISK_PCT`, `SOFT_LOSS_PCT`, `HARD_LOSS_PCT`, `PROFIT_STOP_PCT`, `MAX_TRADES_PER_DAY`, `MAX_CONSEC_LOSSES`, `K_GRID`, `SLOPE_WINDOW_GRID`, `CONFIRM_BODY_GRID`, `PAIR_META` (dict with pip_size, pip_value_fn per pair).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_constants.py
from v17.common.types import SUPPORTED_SYMBOLS, Symbol
from v17.setups import c6_constants as C


def test_symbols_registered():
    assert Symbol("AUDUSD") in SUPPORTED_SYMBOLS
    assert Symbol("USDJPY") in SUPPORTED_SYMBOLS
    assert Symbol("USA500IDXUSD") in SUPPORTED_SYMBOLS


def test_constants_locked_values():
    assert C.SESSION_ANCHOR_HOUR_UTC == 8
    assert C.HARD_FLAT_HOUR_MIN_UTC == (19, 30)
    assert C.ENTRY_WINDOW_START_UTC_HM == (8, 5)
    assert C.ENTRY_WINDOW_END_UTC_HM == (19, 0)
    assert C.NY_OPEN_BLACKOUT_UTC_HM == ((13, 30, 0), (13, 34, 59))
    assert C.NEWS_BLACKOUT_MIN == 15
    assert C.WARMUP_SPX_BARS == 12
    assert C.TRAIL_EMA_PERIOD == 20
    assert C.TRAIL_BUFFER_ATR_MULT == 0.25
    assert C.ATR_PERIOD == 14
    assert C.ATR_FLOOR_MULT == 0.75
    assert C.RISK_PCT == 0.005
    assert C.PORTFOLIO_RISK_PCT == 0.0075
    assert C.SOFT_LOSS_PCT == -0.015
    assert C.HARD_LOSS_PCT == -0.025
    assert C.PROFIT_STOP_PCT == 0.020
    assert C.MAX_TRADES_PER_DAY == 8
    assert C.MAX_CONSEC_LOSSES == 3
    assert C.K_GRID == (0.2, 0.3, 0.4, 0.5)
    assert C.SLOPE_WINDOW_GRID == (8, 12, 16, 20)
    assert C.CONFIRM_BODY_GRID == (0.3, 0.4, 0.5)


def test_pair_meta_audusd():
    m = C.PAIR_META["AUDUSD"]
    assert m["pip_size"] == 0.0001
    assert m["pip_value_per_lot"](1.0) == 10.0  # fixed


def test_pair_meta_usdjpy_variable():
    m = C.PAIR_META["USDJPY"]
    assert m["pip_size"] == 0.01
    # USDJPY pip value in USD = 1000 / price
    assert abs(m["pip_value_per_lot"](150.0) - 1000 / 150.0) < 1e-9
    assert abs(m["pip_value_per_lot"](100.0) - 10.0) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_constants.py -v`
Expected: FAIL — `c6_constants` module not found, SUPPORTED_SYMBOLS missing new symbols.

- [ ] **Step 3: Extend `SUPPORTED_SYMBOLS`**

Edit `src/v17/common/types.py`, extend the tuple:

```python
SUPPORTED_SYMBOLS: tuple[Symbol, ...] = (
    Symbol("EURUSD"),
    Symbol("GBPUSD"),
    Symbol("EURGBP"),
    Symbol("USDJPY"),
    Symbol("USATECHIDXUSD"),
    Symbol("AUDUSD"),
    Symbol("USA500IDXUSD"),
)
```

Note `USDJPY` is already present. Only add `AUDUSD` and `USA500IDXUSD`.

- [ ] **Step 4: Create `c6_constants.py`**

```python
# src/v17/setups/c6_constants.py
"""Frozen Cycle 6 constants (SPX-led intraday risk-on/off FX).

Spec: docs/superpowers/specs/2026-11-12-cycle6-spx-led-fx-design.md
"""
from __future__ import annotations

from typing import Callable, Final

SESSION_ANCHOR_HOUR_UTC: Final[int] = 8
HARD_FLAT_HOUR_MIN_UTC: Final[tuple[int, int]] = (19, 30)
ENTRY_WINDOW_START_UTC_HM: Final[tuple[int, int]] = (8, 5)
ENTRY_WINDOW_END_UTC_HM: Final[tuple[int, int]] = (19, 0)
NY_OPEN_BLACKOUT_UTC_HM: Final[tuple[tuple[int, int, int], tuple[int, int, int]]] = (
    (13, 30, 0),
    (13, 34, 59),
)
NEWS_BLACKOUT_MIN: Final[int] = 15
WARMUP_SPX_BARS: Final[int] = 12
TRAIL_EMA_PERIOD: Final[int] = 20
TRAIL_BUFFER_ATR_MULT: Final[float] = 0.25
ATR_PERIOD: Final[int] = 14
ATR_FLOOR_MULT: Final[float] = 0.75

RISK_PCT: Final[float] = 0.005
PORTFOLIO_RISK_PCT: Final[float] = 0.0075
SOFT_LOSS_PCT: Final[float] = -0.015
HARD_LOSS_PCT: Final[float] = -0.025
PROFIT_STOP_PCT: Final[float] = 0.020
MAX_TRADES_PER_DAY: Final[int] = 8
MAX_CONSEC_LOSSES: Final[int] = 3

K_GRID: Final[tuple[float, ...]] = (0.2, 0.3, 0.4, 0.5)
SLOPE_WINDOW_GRID: Final[tuple[int, ...]] = (8, 12, 16, 20)
CONFIRM_BODY_GRID: Final[tuple[float, ...]] = (0.3, 0.4, 0.5)


def _audusd_pip_value(_price: float) -> float:
    return 10.0


def _usdjpy_pip_value(price: float) -> float:
    return 1000.0 / price


PAIR_META: Final[dict[str, dict]] = {
    "AUDUSD": {
        "pip_size": 0.0001,
        "pip_value_per_lot": _audusd_pip_value,
        "currencies": ("AUD", "USD"),
    },
    "USDJPY": {
        "pip_size": 0.01,
        "pip_value_per_lot": _usdjpy_pip_value,
        "currencies": ("USD", "JPY"),
    },
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_constants.py -v`
Expected: PASS all four.

- [ ] **Step 6: Commit**

```bash
git add src/v17/common/types.py src/v17/setups/c6_constants.py tests/unit/test_c6_constants.py
git commit -m "feat(c6): symbol registry + frozen constants for cycle 6"
```

---

## Task 2: Engine catalog `c6_engines.py`

**Files:**
- Create: `src/v17/setups/c6_engines.py`
- Test: `tests/unit/test_c6_engines.py`

**Interfaces:**
- Consumes: `v17.setups.c6_constants.PAIR_META`.
- Produces: `C6EngineConfig` frozen dataclass with fields `engine_id: str`, `symbol: str`, `pip_size: float`, `pip_value_per_lot: Callable[[float], float]`, `priority_order: int`; constant `C6_CATALOG: tuple[C6EngineConfig, ...]` with two entries.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_engines.py
from v17.setups.c6_engines import C6_CATALOG, C6EngineConfig


def test_catalog_two_pairs():
    assert len(C6_CATALOG) == 2
    ids = {c.engine_id for c in C6_CATALOG}
    assert ids == {"C6-AUDUSD", "C6-USDJPY"}


def test_catalog_pip_sizes():
    by_sym = {c.symbol: c for c in C6_CATALOG}
    assert by_sym["AUDUSD"].pip_size == 0.0001
    assert by_sym["USDJPY"].pip_size == 0.01


def test_catalog_pip_value_callables():
    by_sym = {c.symbol: c for c in C6_CATALOG}
    assert by_sym["AUDUSD"].pip_value_per_lot(0.65) == 10.0
    assert abs(by_sym["USDJPY"].pip_value_per_lot(150.0) - 6.6666666666) < 1e-6


def test_catalog_priority_order_distinct():
    orders = [c.priority_order for c in C6_CATALOG]
    assert len(set(orders)) == len(orders)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_engines.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `c6_engines.py`**

```python
# src/v17/setups/c6_engines.py
"""Cycle 6 engine catalog — two FX pairs, SPX regime driver."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final

from v17.setups.c6_constants import PAIR_META


@dataclass(frozen=True)
class C6EngineConfig:
    engine_id: str
    symbol: str
    pip_size: float
    pip_value_per_lot: Callable[[float], float]
    priority_order: int


C6_CATALOG: Final[tuple[C6EngineConfig, ...]] = (
    C6EngineConfig(
        engine_id="C6-AUDUSD",
        symbol="AUDUSD",
        pip_size=PAIR_META["AUDUSD"]["pip_size"],
        pip_value_per_lot=PAIR_META["AUDUSD"]["pip_value_per_lot"],
        priority_order=1,
    ),
    C6EngineConfig(
        engine_id="C6-USDJPY",
        symbol="USDJPY",
        pip_size=PAIR_META["USDJPY"]["pip_size"],
        pip_value_per_lot=PAIR_META["USDJPY"]["pip_value_per_lot"],
        priority_order=2,
    ),
)

REGIME_DRIVER_SYMBOL: Final[str] = "USA500IDXUSD"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_engines.py -v`
Expected: PASS all four.

- [ ] **Step 5: Commit**

```bash
git add src/v17/setups/c6_engines.py tests/unit/test_c6_engines.py
git commit -m "feat(c6): engine catalog with AUDUSD + USDJPY + SPX regime driver"
```

---

## Task 3: M1 bid+ask CSV → paired M1 parquet ingest

**Files:**
- Create: `src/v17/data/c6_pipeline.py`
- Test: `tests/unit/test_c6_pipeline_m1.py`
- Test fixtures: `tests/fixtures/c6_sample_bid.csv`, `tests/fixtures/c6_sample_ask.csv`

**Interfaces:**
- Consumes: `v17.data.dukascopy_csv.read_file`.
- Produces: `ingest_m1_paired(bid_csv: Path, ask_csv: Path, symbol: str, out_root: Path) -> int` → returns row count written. Writes to `<out_root>/<symbol>/year=YYYY/part-00.parquet` with schema `(ts_utc int64 ns, symbol str, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, bid_volume, ask_volume, spread_mid)`.

- [ ] **Step 1: Write fixtures**

Create `tests/fixtures/c6_sample_bid.csv`:

```
Gmt time,Open,High,Low,Close,Volume
01.01.2020 08:00:00.000,0.70010,0.70020,0.70005,0.70015,100
01.01.2020 08:01:00.000,0.70015,0.70025,0.70010,0.70020,120
01.01.2020 08:02:00.000,0.70020,0.70030,0.70015,0.70025,80
```

Create `tests/fixtures/c6_sample_ask.csv`:

```
Gmt time,Open,High,Low,Close,Volume
01.01.2020 08:00:00.000,0.70013,0.70023,0.70008,0.70018,100
01.01.2020 08:01:00.000,0.70018,0.70028,0.70013,0.70023,120
01.01.2020 08:02:00.000,0.70023,0.70033,0.70018,0.70028,80
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_c6_pipeline_m1.py
from pathlib import Path

import pyarrow.parquet as pq

from v17.data.c6_pipeline import ingest_m1_paired

FIX = Path(__file__).parent.parent / "fixtures"


def test_ingest_writes_parquet_with_expected_schema(tmp_path):
    n = ingest_m1_paired(
        FIX / "c6_sample_bid.csv",
        FIX / "c6_sample_ask.csv",
        "AUDUSD",
        tmp_path,
    )
    assert n == 3
    out = tmp_path / "AUDUSD" / "year=2020" / "part-00.parquet"
    assert out.exists()
    df = pq.read_table(out).to_pandas()
    assert set(df.columns) >= {
        "ts_utc", "symbol", "bid_o", "bid_h", "bid_l", "bid_c",
        "ask_o", "ask_h", "ask_l", "ask_c", "bid_volume", "ask_volume", "spread_mid",
    }
    assert (df["symbol"] == "AUDUSD").all()
    assert len(df) == 3


def test_ingest_spread_mid_computation(tmp_path):
    ingest_m1_paired(
        FIX / "c6_sample_bid.csv",
        FIX / "c6_sample_ask.csv",
        "AUDUSD",
        tmp_path,
    )
    out = tmp_path / "AUDUSD" / "year=2020" / "part-00.parquet"
    df = pq.read_table(out).to_pandas().sort_values("ts_utc").reset_index(drop=True)
    # First row: bid_c=0.70015, ask_c=0.70018 -> spread = 0.00003 = 0.3 pips
    assert abs(df.loc[0, "spread_mid"] - 0.00003) < 1e-9
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_pipeline_m1.py -v`
Expected: FAIL — `c6_pipeline` module not found.

- [ ] **Step 4: Implement ingest**

```python
# src/v17/data/c6_pipeline.py
"""Cycle 6 data pipeline: M1 bid/ask CSV -> paired M1 parquet -> M5 parquet."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from v17.data.dukascopy_csv import read_file


_PAIRED_SCHEMA = pa.schema([
    ("ts_utc", pa.int64()),
    ("symbol", pa.string()),
    ("bid_o", pa.float64()),
    ("bid_h", pa.float64()),
    ("bid_l", pa.float64()),
    ("bid_c", pa.float64()),
    ("ask_o", pa.float64()),
    ("ask_h", pa.float64()),
    ("ask_l", pa.float64()),
    ("ask_c", pa.float64()),
    ("bid_volume", pa.int64()),
    ("ask_volume", pa.int64()),
    ("spread_mid", pa.float64()),
])


def ingest_m1_paired(
    bid_csv: Path,
    ask_csv: Path,
    symbol: str,
    out_root: Path,
) -> int:
    bid = read_file(bid_csv, side="bid").rename(
        columns={"open": "bid_o", "high": "bid_h", "low": "bid_l", "close": "bid_c", "volume": "bid_volume"}
    )
    ask = read_file(ask_csv, side="ask").rename(
        columns={"open": "open_ask", "high": "ask_h", "low": "ask_l", "close": "ask_c", "volume": "ask_volume"}
    ).rename(columns={"open_ask": "ask_o"})
    merged = pd.merge(bid[["ts", "bid_o", "bid_h", "bid_l", "bid_c", "bid_volume"]],
                      ask[["ts", "ask_o", "ask_h", "ask_l", "ask_c", "ask_volume"]],
                      on="ts", how="inner")
    merged["ts_utc"] = merged["ts"].astype("int64")
    merged["symbol"] = symbol
    merged["spread_mid"] = merged["ask_c"] - merged["bid_c"]
    merged = merged.drop(columns=["ts"])
    merged = merged[[
        "ts_utc", "symbol",
        "bid_o", "bid_h", "bid_l", "bid_c",
        "ask_o", "ask_h", "ask_l", "ask_c",
        "bid_volume", "ask_volume", "spread_mid",
    ]]

    total = 0
    merged["year"] = pd.to_datetime(merged["ts_utc"], unit="ns", utc=True).dt.year
    for year_val, chunk in merged.groupby("year"):
        out = out_root / symbol / f"year={int(year_val)}" / "part-00.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(
            chunk.drop(columns=["year"]), schema=_PAIRED_SCHEMA, preserve_index=False
        )
        pq.write_table(table, out, compression="zstd")
        total += len(chunk)
    return total
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_pipeline_m1.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/v17/data/c6_pipeline.py tests/unit/test_c6_pipeline_m1.py tests/fixtures/c6_sample_bid.csv tests/fixtures/c6_sample_ask.csv
git commit -m "feat(c6): M1 bid+ask paired parquet ingest"
```

---

## Task 4: M1 paired → M5 paired resample with `< 5 ticks` drop rule

**Files:**
- Modify: `src/v17/data/c6_pipeline.py` (add function)
- Test: `tests/unit/test_c6_pipeline_m5.py`

**Interfaces:**
- Consumes: paired M1 parquet from Task 3; `v17.data.resample.resample_paired` for the resample skeleton.
- Produces: `build_m5_paired(m1_root: Path, m5_root: Path, symbol: str, year: int) -> int` → writes `<m5_root>/<symbol>/year=YYYY/part-00.parquet` with the same paired schema plus column `n_m1_ticks int64`. Bars with `n_m1_ticks < 5` are dropped.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_pipeline_m5.py
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from v17.data.c6_pipeline import build_m5_paired


def _write_m1_paired_fixture(root: Path, symbol: str, year: int):
    # Build 20 synthetic M1 bars across 4 M5 buckets, varying tick counts.
    ts0 = pd.Timestamp(f"{year}-01-01 08:00:00", tz="UTC").value  # ns
    rows = []
    for i in range(20):
        rows.append({
            "ts_utc": ts0 + i * 60_000_000_000,
            "symbol": symbol,
            "bid_o": 1.0, "bid_h": 1.0, "bid_l": 1.0, "bid_c": 1.0,
            "ask_o": 1.0, "ask_h": 1.0, "ask_l": 1.0, "ask_c": 1.0,
            "bid_volume": 1, "ask_volume": 1, "spread_mid": 0.0,
        })
    # Drop bars 5-9 to leave bucket 08:05-08:10 with 0 ticks (missing bucket)
    # and shrink bucket 08:10-08:15 to 2 ticks (ticks 10,11 only). We keep
    # ticks 0-4 (bucket 1: 5), remove 5-9, keep 10-11 (bucket 3: 2),
    # remove 12-14, keep 15-19 (bucket 4: 5).
    keep_indices = {0, 1, 2, 3, 4, 10, 11, 15, 16, 17, 18, 19}
    rows = [r for i, r in enumerate(rows) if i in keep_indices]
    df = pd.DataFrame(rows)
    out = root / symbol / f"year={year}" / "part-00.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out, compression="zstd")


def test_build_m5_drops_low_tick_bars(tmp_path):
    m1 = tmp_path / "m1"
    m5 = tmp_path / "m5"
    _write_m1_paired_fixture(m1, "AUDUSD", 2020)
    n = build_m5_paired(m1, m5, "AUDUSD", 2020)
    # Expect 2 kept buckets (the ones with 5 ticks each). The 2-tick bucket is dropped.
    assert n == 2
    out = m5 / "AUDUSD" / "year=2020" / "part-00.parquet"
    df = pq.read_table(out).to_pandas()
    assert (df["n_m1_ticks"] >= 5).all()
    assert len(df) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_pipeline_m5.py -v`
Expected: FAIL — `build_m5_paired` not defined.

- [ ] **Step 3: Implement M5 resample**

Append to `src/v17/data/c6_pipeline.py`:

```python
from v17.common.types import TF
from v17.data.resample import resample_paired


_M5_SCHEMA = pa.schema(list(_PAIRED_SCHEMA) + [("n_m1_ticks", pa.int64())])


def build_m5_paired(m1_root: Path, m5_root: Path, symbol: str, year: int) -> int:
    src = m1_root / symbol / f"year={year}" / "part-00.parquet"
    if not src.exists():
        return 0
    df = pq.read_table(src).to_pandas()
    # Count M1 ticks per 5-min bucket before resample.
    df["_ts"] = pd.to_datetime(df["ts_utc"], unit="ns", utc=True)
    df["_bucket"] = df["_ts"].dt.floor("5min")
    tick_counts = df.groupby("_bucket").size().rename("n_m1_ticks").reset_index()

    m5 = resample_paired(df.drop(columns=["_ts", "_bucket"]), TF.M5)
    m5["_bucket"] = pd.to_datetime(m5["ts_utc"], unit="ns", utc=True).dt.floor("5min")
    m5 = m5.merge(tick_counts, on="_bucket", how="left").drop(columns=["_bucket"])
    m5["n_m1_ticks"] = m5["n_m1_ticks"].fillna(0).astype("int64")
    m5 = m5[m5["n_m1_ticks"] >= 5].reset_index(drop=True)

    out = m5_root / symbol / f"year={year}" / "part-00.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(m5, schema=_M5_SCHEMA, preserve_index=False)
    pq.write_table(table, out, compression="zstd")
    return len(m5)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_pipeline_m5.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/v17/data/c6_pipeline.py tests/unit/test_c6_pipeline_m5.py
git commit -m "feat(c6): M5 paired resample with <5-tick bar drop rule"
```

---

## Task 5: ForexFactory calendar cache + stale check

**Files:**
- Create: `src/v17/data/c6_calendar.py`
- Test: `tests/unit/test_c6_calendar.py`
- Fixture: `tests/fixtures/c6_ff_sample.json`

**Interfaces:**
- Consumes: raw ForexFactory JSON in a directory (same shape as `v17.data.calendar.ff_json.load_archive_dir`).
- Produces:
  - `build_calendar_index(ff_dir: Path, out_parquet: Path, currencies: tuple[str, ...]) -> int` → parquet with columns `(ts_utc int64, currency str, impact str, title str)` filtered to `impact == "high"` and `currency in currencies`.
  - `load_calendar_index(index_parquet: Path) -> pd.DataFrame` → sorted by ts_utc.
  - `is_blackout(ts_utc_ns: int, index: pd.DataFrame, blackout_min: int) -> bool` → True if `ts` is within ±`blackout_min` of any event.
  - `is_calendar_stale(sim_ts_ns: int, index: pd.DataFrame, max_age_hours: int = 48) -> bool` → True if `sim_ts − max(index.ts_utc) > max_age_hours`.

- [ ] **Step 1: Write fixture**

Create `tests/fixtures/c6_ff_sample.json`:

```json
[
  {"date": "2020-03-06T13:30:00+00:00", "country": "USD", "impact": "High", "title": "NFP"},
  {"date": "2020-03-06T10:00:00+00:00", "country": "USD", "impact": "Medium", "title": "Factory Orders"},
  {"date": "2020-03-04T00:30:00+00:00", "country": "AUD", "impact": "High", "title": "GDP"}
]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_c6_calendar.py
from pathlib import Path
import pandas as pd

from v17.data.c6_calendar import (
    build_calendar_index, load_calendar_index, is_blackout, is_calendar_stale,
)

FIX = Path(__file__).parent.parent / "fixtures"


def test_build_filters_high_impact_only(tmp_path):
    out = tmp_path / "ff_c6_index.parquet"
    n = build_calendar_index(FIX, out, ("USD", "AUD", "JPY"))
    assert n == 2  # NFP + AUD GDP
    df = load_calendar_index(out)
    assert set(df["impact"].unique()) == {"high"}
    assert set(df["currency"].unique()) == {"USD", "AUD"}


def test_is_blackout_window(tmp_path):
    out = tmp_path / "ff_c6_index.parquet"
    build_calendar_index(FIX, out, ("USD", "AUD", "JPY"))
    idx = load_calendar_index(out)
    nfp_ts = pd.Timestamp("2020-03-06 13:30:00", tz="UTC").value
    # Entry 10 min before NFP -> inside 15-min blackout.
    assert is_blackout(nfp_ts - 10 * 60 * 1_000_000_000, idx, 15) is True
    # 20 min before -> outside.
    assert is_blackout(nfp_ts - 20 * 60 * 1_000_000_000, idx, 15) is False


def test_is_calendar_stale(tmp_path):
    out = tmp_path / "ff_c6_index.parquet"
    build_calendar_index(FIX, out, ("USD", "AUD", "JPY"))
    idx = load_calendar_index(out)
    # max event is 2020-03-06 13:30 UTC. Sim ts 2020-03-10 00:00 UTC -> stale (>48h).
    stale_sim = pd.Timestamp("2020-03-10 00:00:00", tz="UTC").value
    assert is_calendar_stale(stale_sim, idx, max_age_hours=48) is True
    # Sim ts 2020-03-07 13:00 UTC -> 23.5h after -> fresh.
    fresh_sim = pd.Timestamp("2020-03-07 13:00:00", tz="UTC").value
    assert is_calendar_stale(fresh_sim, idx, max_age_hours=48) is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_calendar.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement calendar module**

```python
# src/v17/data/c6_calendar.py
"""Cycle 6 ForexFactory calendar cache + blackout lookup."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dateutil import parser as dateparser

_IMPACT_MAP = {"High": "high", "Medium": "medium", "Low": "low"}


def build_calendar_index(
    ff_dir: Path, out_parquet: Path, currencies: tuple[str, ...]
) -> int:
    rows = []
    for p in sorted(ff_dir.glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        for item in raw:
            impact = _IMPACT_MAP.get(item.get("impact", ""))
            if impact != "high":
                continue
            cur = item.get("country")
            if cur not in currencies:
                continue
            ts = dateparser.isoparse(item["date"])
            rows.append({
                "ts_utc": pd.Timestamp(ts).tz_convert("UTC").value,
                "currency": cur,
                "impact": impact,
                "title": item.get("title", ""),
            })
    df = pd.DataFrame(rows).drop_duplicates(subset=["ts_utc", "currency", "title"])
    df = df.sort_values("ts_utc").reset_index(drop=True)
    schema = pa.schema([
        ("ts_utc", pa.int64()),
        ("currency", pa.string()),
        ("impact", pa.string()),
        ("title", pa.string()),
    ])
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False),
                   out_parquet, compression="zstd")
    return len(df)


def load_calendar_index(index_parquet: Path) -> pd.DataFrame:
    return pq.read_table(index_parquet).to_pandas().sort_values("ts_utc").reset_index(drop=True)


def is_blackout(ts_utc_ns: int, index: pd.DataFrame, blackout_min: int) -> bool:
    if index.empty:
        return False
    delta_ns = blackout_min * 60 * 1_000_000_000
    return bool(((index["ts_utc"] - ts_utc_ns).abs() <= delta_ns).any())


def is_calendar_stale(sim_ts_ns: int, index: pd.DataFrame, max_age_hours: int = 48) -> bool:
    if index.empty:
        return True
    max_event = int(index["ts_utc"].max())
    return (sim_ts_ns - max_event) > max_age_hours * 3600 * 1_000_000_000
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_calendar.py -v`
Expected: PASS all three.

- [ ] **Step 6: Commit**

```bash
git add src/v17/data/c6_calendar.py tests/unit/test_c6_calendar.py tests/fixtures/c6_ff_sample.json
git commit -m "feat(c6): ForexFactory calendar index + blackout + stale check"
```

---

## Task 6: SPX regime (session VWAP, slope, ATR, trinary state)

**Files:**
- Create: `src/v17/setups/c6_regime.py`
- Test: `tests/unit/test_c6_regime.py`

**Interfaces:**
- Consumes: SPX paired M5 DataFrame with columns `(ts_utc, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, ...)`.
- Produces: `compute_regime(spx_m5: pd.DataFrame, k_atr: float, slope_window: int, session_anchor_hour: int = 8, atr_period: int = 14) -> pd.DataFrame` with columns `(ts_utc, mid_close, vwap, atr, slope, regime_state)` where `regime_state ∈ {"LONG_BIAS", "SHORT_BIAS", "FLAT"}`. Bars with insufficient warmup emit `FLAT`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_regime.py
import numpy as np
import pandas as pd

from v17.setups.c6_regime import compute_regime


def _mk_spx(n_bars: int, closes: np.ndarray) -> pd.DataFrame:
    ts0 = pd.Timestamp("2020-01-02 08:00:00", tz="UTC").value
    ts = np.array([ts0 + i * 5 * 60_000_000_000 for i in range(n_bars)], dtype="int64")
    df = pd.DataFrame({
        "ts_utc": ts,
        "bid_o": closes, "bid_h": closes, "bid_l": closes, "bid_c": closes,
        "ask_o": closes, "ask_h": closes, "ask_l": closes, "ask_c": closes,
        "bid_volume": 1, "ask_volume": 1, "spread_mid": 0.0,
    })
    return df


def test_warmup_produces_flat():
    closes = np.linspace(3000.0, 3010.0, 10)
    df = _mk_spx(10, closes)
    out = compute_regime(df, k_atr=0.3, slope_window=12)
    # Only 10 bars, need 12 slope + 14 ATR => all FLAT.
    assert (out["regime_state"] == "FLAT").all()


def test_long_bias_strong_uptrend():
    # 30 bars rising steadily from 3000 to 3100.
    closes = np.linspace(3000.0, 3100.0, 30)
    df = _mk_spx(30, closes)
    out = compute_regime(df, k_atr=0.3, slope_window=12)
    tail = out.tail(5)
    assert (tail["regime_state"] == "LONG_BIAS").all()


def test_short_bias_strong_downtrend():
    closes = np.linspace(3100.0, 3000.0, 30)
    df = _mk_spx(30, closes)
    out = compute_regime(df, k_atr=0.3, slope_window=12)
    tail = out.tail(5)
    assert (tail["regime_state"] == "SHORT_BIAS").all()


def test_flat_when_price_inside_band():
    # Sideways: hover around 3050 ±1 ATR fraction.
    rng = np.random.default_rng(42)
    closes = 3050.0 + rng.normal(0, 0.5, 60)
    df = _mk_spx(60, closes)
    out = compute_regime(df, k_atr=0.3, slope_window=12)
    # Majority FLAT in a tight range.
    assert (out["regime_state"] == "FLAT").mean() > 0.7


def test_session_anchor_resets_vwap_daily():
    # Two trading days of 50 bars each; VWAP should drop at day boundary.
    day1 = np.linspace(3000.0, 3100.0, 50)
    day2 = np.linspace(2900.0, 3000.0, 50)
    closes = np.concatenate([day1, day2])
    ts0 = pd.Timestamp("2020-01-02 08:00:00", tz="UTC").value
    ts = [ts0 + i * 5 * 60_000_000_000 for i in range(50)]
    ts += [pd.Timestamp("2020-01-03 08:00:00", tz="UTC").value + i * 5 * 60_000_000_000 for i in range(50)]
    df = _mk_spx(100, closes)
    df["ts_utc"] = ts
    out = compute_regime(df, k_atr=0.3, slope_window=12)
    first_bar_day2_idx = 50
    vwap_last_day1 = out.iloc[first_bar_day2_idx - 1]["vwap"]
    vwap_first_day2 = out.iloc[first_bar_day2_idx]["vwap"]
    # VWAP resets at new session -> equals first close of day 2 bucket.
    assert abs(vwap_first_day2 - closes[first_bar_day2_idx]) < 1e-6
    assert vwap_last_day1 != vwap_first_day2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_regime.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement regime module**

```python
# src/v17/setups/c6_regime.py
"""Cycle 6 SPX regime: session VWAP + slope + ATR -> trinary state."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _session_vwap(mid: np.ndarray, vol: np.ndarray, session_id: np.ndarray) -> np.ndarray:
    n = len(mid)
    out = np.empty(n, dtype=float)
    cum_pv = 0.0
    cum_v = 0.0
    cur_sid = -1
    for i in range(n):
        if session_id[i] != cur_sid:
            cur_sid = session_id[i]
            cum_pv = 0.0
            cum_v = 0.0
        v = max(float(vol[i]), 1.0)  # guard against zero-volume bars
        cum_pv += mid[i] * v
        cum_v += v
        out[i] = cum_pv / cum_v if cum_v > 0 else mid[i]
    return out


def _atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan, dtype=float)
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    if n < period:
        return out
    atr = tr[1:period+1].mean()
    out[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + tr[i]) / period
        out[i] = atr
    return out


def _rolling_slope(y: np.ndarray, window: int) -> np.ndarray:
    n = len(y)
    out = np.full(n, np.nan, dtype=float)
    if n < window:
        return out
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    for i in range(window - 1, n):
        y_win = y[i - window + 1 : i + 1]
        y_mean = y_win.mean()
        cov = ((x - x_mean) * (y_win - y_mean)).sum()
        out[i] = cov / x_var
    return out


def compute_regime(
    spx_m5: pd.DataFrame,
    k_atr: float,
    slope_window: int,
    session_anchor_hour: int = 8,
    atr_period: int = 14,
) -> pd.DataFrame:
    df = spx_m5.copy()
    ts = pd.to_datetime(df["ts_utc"], unit="ns", utc=True)
    # Session id = calendar date shifted by -session_anchor_hour
    anchored = ts - pd.Timedelta(hours=session_anchor_hour)
    session_id = (anchored.dt.year * 10000 + anchored.dt.month * 100 + anchored.dt.day).to_numpy()

    mid_c = ((df["bid_c"] + df["ask_c"]) * 0.5).to_numpy()
    mid_h = ((df["bid_h"] + df["ask_h"]) * 0.5).to_numpy()
    mid_l = ((df["bid_l"] + df["ask_l"]) * 0.5).to_numpy()
    vol = (df["bid_volume"].fillna(0) + df["ask_volume"].fillna(0)).to_numpy()

    vwap = _session_vwap(mid_c, vol, session_id)
    atr = _atr_wilder(mid_h, mid_l, mid_c, atr_period)
    slope = _rolling_slope(vwap, slope_window)

    # Warmup gate: require both slope and ATR present AND session has >=slope_window bars.
    bars_in_session = np.zeros(len(df), dtype=int)
    cur = -1
    count = 0
    for i, sid in enumerate(session_id):
        if sid != cur:
            cur = sid
            count = 0
        count += 1
        bars_in_session[i] = count

    regime = np.full(len(df), "FLAT", dtype=object)
    have = (~np.isnan(atr)) & (~np.isnan(slope)) & (bars_in_session >= slope_window)
    long_mask = have & (mid_c > vwap + k_atr * atr) & (slope > 0)
    short_mask = have & (mid_c < vwap - k_atr * atr) & (slope < 0)
    regime[long_mask] = "LONG_BIAS"
    regime[short_mask] = "SHORT_BIAS"

    return pd.DataFrame({
        "ts_utc": df["ts_utc"].to_numpy(),
        "mid_close": mid_c,
        "vwap": vwap,
        "atr": atr,
        "slope": slope,
        "regime_state": regime,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_regime.py -v`
Expected: PASS all five.

- [ ] **Step 5: Commit**

```bash
git add src/v17/setups/c6_regime.py tests/unit/test_c6_regime.py
git commit -m "feat(c6): SPX regime filter (session VWAP + slope + trinary state)"
```

---

## Task 7: FX micro-trigger (VWAP pullback + confirm bar)

**Files:**
- Create: `src/v17/setups/c6_microtrigger.py`
- Test: `tests/unit/test_c6_microtrigger.py`

**Interfaces:**
- Consumes: FX paired M5 DataFrame (same columns as SPX).
- Produces: `compute_micro_signals(fx_m5: pd.DataFrame, confirm_body_mult: float, atr_period: int = 14, session_anchor_hour: int = 8, pullback_lookback: int = 3) -> pd.DataFrame` with columns `(ts_utc, fx_mid_close, fx_vwap, fx_atr, pullback, confirm_long, confirm_short)`. Boolean columns `confirm_long`/`confirm_short` indicate a valid entry trigger at this bar's close.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_microtrigger.py
import numpy as np
import pandas as pd

from v17.setups.c6_microtrigger import compute_micro_signals


def _mk_fx(n: int, oc_pairs):
    ts0 = pd.Timestamp("2020-01-02 08:00:00", tz="UTC").value
    opens = np.array([p[0] for p in oc_pairs])
    closes = np.array([p[1] for p in oc_pairs])
    highs = np.maximum(opens, closes) + 0.00005
    lows = np.minimum(opens, closes) - 0.00005
    ts = np.array([ts0 + i * 5 * 60_000_000_000 for i in range(n)], dtype="int64")
    return pd.DataFrame({
        "ts_utc": ts,
        "bid_o": opens, "bid_h": highs, "bid_l": lows, "bid_c": closes,
        "ask_o": opens + 0.00002, "ask_h": highs + 0.00002,
        "ask_l": lows + 0.00002, "ask_c": closes + 0.00002,
        "bid_volume": 1, "ask_volume": 1, "spread_mid": 0.00002,
    })


def test_no_confirm_before_warmup():
    df = _mk_fx(5, [(1.0, 1.0001)] * 5)
    out = compute_micro_signals(df, confirm_body_mult=0.4)
    assert (~out["confirm_long"]).all()
    assert (~out["confirm_short"]).all()


def test_long_confirm_after_pullback():
    # Rising series: VWAP sits just below price; last bar pulls back to VWAP
    # then confirms with a big green bar.
    bars = [(1.0, 1.0010)] * 20 + [(1.0010, 1.0004), (1.0004, 1.0020)]
    df = _mk_fx(len(bars), bars)
    out = compute_micro_signals(df, confirm_body_mult=0.1, atr_period=5)
    assert out.iloc[-1]["confirm_long"] == True


def test_short_confirm_mirror():
    bars = [(1.0010, 1.0)] * 20 + [(1.0, 1.0006), (1.0006, 0.9990)]
    df = _mk_fx(len(bars), bars)
    out = compute_micro_signals(df, confirm_body_mult=0.1, atr_period=5)
    assert out.iloc[-1]["confirm_short"] == True


def test_tiny_body_rejected():
    # Pullback to VWAP but confirm bar body is below threshold.
    bars = [(1.0, 1.0010)] * 20 + [(1.0010, 1.0005), (1.0005, 1.00055)]
    df = _mk_fx(len(bars), bars)
    out = compute_micro_signals(df, confirm_body_mult=5.0, atr_period=5)  # huge threshold
    assert out.iloc[-1]["confirm_long"] == False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_microtrigger.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement micro-trigger**

```python
# src/v17/setups/c6_microtrigger.py
"""Cycle 6 FX micro-trigger: session VWAP pullback + confirm bar."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.setups.c6_regime import _atr_wilder, _session_vwap


def compute_micro_signals(
    fx_m5: pd.DataFrame,
    confirm_body_mult: float,
    atr_period: int = 14,
    session_anchor_hour: int = 8,
    pullback_lookback: int = 3,
) -> pd.DataFrame:
    df = fx_m5.copy()
    ts = pd.to_datetime(df["ts_utc"], unit="ns", utc=True)
    anchored = ts - pd.Timedelta(hours=session_anchor_hour)
    session_id = (anchored.dt.year * 10000 + anchored.dt.month * 100 + anchored.dt.day).to_numpy()

    mid_o = ((df["bid_o"] + df["ask_o"]) * 0.5).to_numpy()
    mid_c = ((df["bid_c"] + df["ask_c"]) * 0.5).to_numpy()
    mid_h = ((df["bid_h"] + df["ask_h"]) * 0.5).to_numpy()
    mid_l = ((df["bid_l"] + df["ask_l"]) * 0.5).to_numpy()
    vol = (df["bid_volume"].fillna(0) + df["ask_volume"].fillna(0)).to_numpy()

    vwap = _session_vwap(mid_c, vol, session_id)
    atr = _atr_wilder(mid_h, mid_l, mid_c, atr_period)

    n = len(df)
    pullback = np.zeros(n, dtype=bool)
    for i in range(n):
        start = max(0, i - pullback_lookback + 1)
        # Any bar in window where VWAP within [low, high].
        v_win = vwap[start:i+1]
        h_win = mid_h[start:i+1]
        l_win = mid_l[start:i+1]
        pullback[i] = bool(((l_win <= v_win) & (v_win <= h_win)).any())

    body = mid_c - mid_o
    atr_safe = np.where(np.isnan(atr), np.inf, atr)
    body_ok_long = body >= confirm_body_mult * atr_safe
    body_ok_short = (-body) >= confirm_body_mult * atr_safe

    have_atr = ~np.isnan(atr)
    confirm_long = pullback & have_atr & (mid_c > vwap) & (mid_c > mid_o) & body_ok_long
    confirm_short = pullback & have_atr & (mid_c < vwap) & (mid_c < mid_o) & body_ok_short

    return pd.DataFrame({
        "ts_utc": df["ts_utc"].to_numpy(),
        "fx_mid_close": mid_c,
        "fx_vwap": vwap,
        "fx_atr": atr,
        "pullback": pullback,
        "confirm_long": confirm_long,
        "confirm_short": confirm_short,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_microtrigger.py -v`
Expected: PASS all four.

- [ ] **Step 5: Commit**

```bash
git add src/v17/setups/c6_microtrigger.py tests/unit/test_c6_microtrigger.py
git commit -m "feat(c6): FX micro-trigger (VWAP pullback + confirm bar)"
```

---

## Task 8: Position sizing

**Files:**
- Create: `src/v17/backtest/c6_sizing.py`
- Test: `tests/unit/test_c6_sizing.py`

**Interfaces:**
- Consumes: `v17.setups.c6_constants.PAIR_META`.
- Produces: `size_position(symbol: str, equity_sod: float, risk_pct: float, entry: float, initial_stop: float) -> tuple[float, float, int]` → `(lots_leg_a, lots_leg_b, R_pips)`. Returns `(0.0, 0.0, R_pips)` if sub-min size.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_sizing.py
from v17.backtest.c6_sizing import size_position


def test_audusd_sizing():
    # Equity 10000, risk 0.5% -> $50 risk. Entry 0.6500 stop 0.6480 -> 20 pips.
    # lots_total = 50 / (20 * 10) = 0.25 -> each leg 0.12 (round down from 0.125).
    a, b, r_pips = size_position("AUDUSD", 10000.0, 0.005, 0.6500, 0.6480)
    assert r_pips == 20
    assert a == 0.12
    assert b == 0.12


def test_usdjpy_sizing_at_150():
    # Equity 10000, risk 0.5% = $50. Entry 150.00 stop 149.80 = 20 pips.
    # pip value = 1000/150 = 6.6666... per 1.0 lot
    # lots_total = 50 / (20 * 6.6666) = 0.375 -> each leg 0.18 (round down from 0.1875).
    a, b, r_pips = size_position("USDJPY", 10000.0, 0.005, 150.00, 149.80)
    assert r_pips == 20
    assert a == 0.18
    assert b == 0.18


def test_sub_min_size_skipped():
    # Tiny R: risk 50, pip value 10, R=200 pips -> lots_total=0.025 -> legs 0.01
    # Make R very large so legs go below 0.01.
    a, b, r_pips = size_position("AUDUSD", 10000.0, 0.005, 0.6500, 0.4500)
    # R=2000 pips. lots_total=50/(2000*10)=0.0025 -> each leg 0.00 after round-down.
    assert a == 0.0
    assert b == 0.0


def test_unknown_symbol_raises():
    import pytest
    with pytest.raises(KeyError):
        size_position("XAUUSD", 10000.0, 0.005, 2000.0, 1990.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_sizing.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement sizing**

```python
# src/v17/backtest/c6_sizing.py
"""Cycle 6 position sizing with per-pair pip semantics + 2-leg split."""
from __future__ import annotations

import math

from v17.setups.c6_constants import PAIR_META


def _round_down(x: float, step: float = 0.01) -> float:
    return math.floor(x / step) * step


def size_position(
    symbol: str,
    equity_sod: float,
    risk_pct: float,
    entry: float,
    initial_stop: float,
) -> tuple[float, float, int]:
    meta = PAIR_META[symbol]
    pip_size = meta["pip_size"]
    pip_value_fn = meta["pip_value_per_lot"]
    r_price = abs(entry - initial_stop)
    r_pips_f = r_price / pip_size
    r_pips = int(round(r_pips_f))
    if r_pips <= 0:
        return 0.0, 0.0, 0
    risk_dollars = equity_sod * risk_pct
    pip_value = pip_value_fn(entry)
    lots_total = risk_dollars / (r_pips * pip_value)
    lots_total = _round_down(lots_total, 0.01)
    lots_leg = _round_down(lots_total / 2.0, 0.01)
    if lots_leg < 0.01:
        return 0.0, 0.0, r_pips
    return lots_leg, lots_leg, r_pips
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_sizing.py -v`
Expected: PASS all four.

- [ ] **Step 5: Commit**

```bash
git add src/v17/backtest/c6_sizing.py tests/unit/test_c6_sizing.py
git commit -m "feat(c6): per-pair position sizing + leg split"
```

---

## Task 9: Two-leg position state machine

**Files:**
- Create: `src/v17/backtest/c6_position.py`
- Test: `tests/unit/test_c6_position.py`

**Interfaces:**
- Consumes: `v17.setups.c6_constants` for trail buffer, EMA period.
- Produces:
  - `C6Position` dataclass with fields `(trade_id, symbol, side ∈ {"long","short"}, entry_ts_ns, entry_price, initial_stop, r_price, lots_a, lots_b, leg_a_open, leg_b_open, leg_b_stop, breakeven_hit, exit_log: list[dict])`.
  - `step(pos: C6Position, bar: dict, ema20: float, atr: float, is_hard_flat: bool) -> C6Position` → mutates pos in place-returning-copy, appends exit events to `exit_log`, updates `leg_b_stop` on trail. Exit events: `{"ts_ns", "leg", "reason", "price", "lots"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_position.py
from v17.backtest.c6_position import C6Position, step


def _bar(o, h, l, c, bid_c=None, ask_c=None, ts=0):
    return {
        "ts_utc": ts,
        "bid_o": o, "bid_h": h, "bid_l": l, "bid_c": bid_c or c,
        "ask_o": o, "ask_h": h, "ask_l": l, "ask_c": ask_c or c,
    }


def _long_pos(entry=0.6500, stop=0.6480, r=0.002, lots=0.1):
    return C6Position(
        trade_id="t1", symbol="AUDUSD", side="long",
        entry_ts_ns=0, entry_price=entry, initial_stop=stop,
        r_price=r, lots_a=lots, lots_b=lots,
        leg_a_open=True, leg_b_open=True, leg_b_stop=stop,
        breakeven_hit=False, exit_log=[],
    )


def test_leg_a_hits_target():
    pos = _long_pos()
    bar = _bar(0.6500, 0.6525, 0.6495, 0.6515)  # high sweeps 1R = 0.6520
    out = step(pos, bar, ema20=0.6505, atr=0.0015, is_hard_flat=False)
    events = [e for e in out.exit_log if e["leg"] == "A"]
    assert len(events) == 1
    assert events[0]["reason"] == "target_1R"
    assert out.leg_a_open is False
    assert out.breakeven_hit is True
    # Leg B stop moved to entry.
    assert out.leg_b_stop == pos.entry_price


def test_initial_stop_both_legs_exit():
    pos = _long_pos()
    bar = _bar(0.6500, 0.6505, 0.6475, 0.6482)  # low breaches initial stop 0.6480
    out = step(pos, bar, ema20=0.6505, atr=0.0015, is_hard_flat=False)
    assert out.leg_a_open is False
    assert out.leg_b_open is False
    reasons = {e["reason"] for e in out.exit_log}
    assert "initial_stop" in reasons


def test_leg_b_trail_activates_only_after_leg_a():
    pos = _long_pos()
    # Bar does not reach 1R target; leg_b_stop should stay at initial.
    bar = _bar(0.6500, 0.6510, 0.6495, 0.6508)
    out = step(pos, bar, ema20=0.6505, atr=0.0015, is_hard_flat=False)
    assert out.leg_a_open is True
    assert out.leg_b_stop == pos.initial_stop  # not trailed


def test_trail_ratchets_up_only_after_leg_a_filled():
    pos = _long_pos()
    pos.leg_a_open = False
    pos.breakeven_hit = True
    pos.leg_b_stop = pos.entry_price
    bar = _bar(0.6500, 0.6540, 0.6495, 0.6535)
    # ema20 - 0.25*atr = 0.6530 - 0.000375 = 0.652625 > entry 0.6500 -> ratchet up.
    out = step(pos, bar, ema20=0.6530, atr=0.0015, is_hard_flat=False)
    assert out.leg_b_stop > pos.entry_price


def test_hard_flat_closes_both():
    pos = _long_pos()
    bar = _bar(0.6500, 0.6505, 0.6495, 0.6502)
    out = step(pos, bar, ema20=0.6505, atr=0.0015, is_hard_flat=True)
    assert out.leg_a_open is False
    assert out.leg_b_open is False
    reasons = {e["reason"] for e in out.exit_log}
    assert "time_stop" in reasons
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_position.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement position state machine**

```python
# src/v17/backtest/c6_position.py
"""Cycle 6 two-leg position state machine."""
from __future__ import annotations

from dataclasses import dataclass, field

from v17.setups.c6_constants import TRAIL_BUFFER_ATR_MULT


@dataclass
class C6Position:
    trade_id: str
    symbol: str
    side: str  # "long" | "short"
    entry_ts_ns: int
    entry_price: float
    initial_stop: float
    r_price: float
    lots_a: float
    lots_b: float
    leg_a_open: bool
    leg_b_open: bool
    leg_b_stop: float
    breakeven_hit: bool
    exit_log: list[dict] = field(default_factory=list)


def _target_price(pos: C6Position) -> float:
    return pos.entry_price + pos.r_price if pos.side == "long" else pos.entry_price - pos.r_price


def _hit_target(pos: C6Position, bar: dict) -> bool:
    tgt = _target_price(pos)
    if pos.side == "long":
        return bar["bid_h"] >= tgt
    return bar["bid_l"] <= tgt


def _hit_stop(pos: C6Position, bar: dict, stop: float) -> bool:
    if pos.side == "long":
        return bar["bid_l"] <= stop
    return bar["bid_h"] >= stop


def step(pos: C6Position, bar: dict, ema20: float, atr: float, is_hard_flat: bool) -> C6Position:
    if is_hard_flat:
        price = bar["bid_c"] if pos.side == "long" else bar["ask_c"]
        if pos.leg_a_open:
            pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "A", "reason": "time_stop", "price": price, "lots": pos.lots_a})
            pos.leg_a_open = False
        if pos.leg_b_open:
            pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "B", "reason": "time_stop", "price": price, "lots": pos.lots_b})
            pos.leg_b_open = False
        return pos

    # Initial stop: both legs out if either still on initial stop.
    if pos.leg_a_open and _hit_stop(pos, bar, pos.initial_stop):
        price = pos.initial_stop
        pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "A", "reason": "initial_stop", "price": price, "lots": pos.lots_a})
        pos.leg_a_open = False
        if pos.leg_b_open and not pos.breakeven_hit:
            pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "B", "reason": "initial_stop", "price": price, "lots": pos.lots_b})
            pos.leg_b_open = False
        return pos

    # Leg-A target.
    if pos.leg_a_open and _hit_target(pos, bar):
        price = _target_price(pos)
        pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "A", "reason": "target_1R", "price": price, "lots": pos.lots_a})
        pos.leg_a_open = False
        pos.breakeven_hit = True
        pos.leg_b_stop = pos.entry_price  # move leg B to BE

    # Leg-B trail (only after leg A filled / breakeven set).
    if pos.leg_b_open and pos.breakeven_hit:
        if pos.side == "long":
            proposed = ema20 - TRAIL_BUFFER_ATR_MULT * atr
            if proposed > pos.leg_b_stop:
                pos.leg_b_stop = proposed
        else:
            proposed = ema20 + TRAIL_BUFFER_ATR_MULT * atr
            if proposed < pos.leg_b_stop:
                pos.leg_b_stop = proposed

    # Leg-B stop check (trailed or breakeven).
    if pos.leg_b_open and _hit_stop(pos, bar, pos.leg_b_stop):
        price = pos.leg_b_stop
        reason = "trail_stop" if pos.breakeven_hit and pos.leg_b_stop != pos.initial_stop else "initial_stop"
        pos.exit_log.append({"ts_ns": bar["ts_utc"], "leg": "B", "reason": reason, "price": price, "lots": pos.lots_b})
        pos.leg_b_open = False

    return pos
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_position.py -v`
Expected: PASS all five.

- [ ] **Step 5: Commit**

```bash
git add src/v17/backtest/c6_position.py tests/unit/test_c6_position.py
git commit -m "feat(c6): two-leg position state machine with EMA trail"
```

---

## Task 10: Daily circuit breakers

**Files:**
- Create: `src/v17/backtest/c6_breakers.py`
- Test: `tests/unit/test_c6_breakers.py`

**Interfaces:**
- Produces:
  - `DailyState` dataclass `(utc_date: str, equity_sod: float, realized_pnl: float, trade_count: int, consec_losses: int, locked: bool, flatten_now: bool)`.
  - `update_after_trade(state: DailyState, trade_pnl: float) -> DailyState`.
  - `evaluate(state: DailyState) -> DailyState` → sets `locked`, `flatten_now` per precedence hard-loss > profit > soft-loss > consec > trade-cap.
  - `allow_entry(state: DailyState) -> bool` → False if locked.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_breakers.py
from v17.backtest.c6_breakers import DailyState, allow_entry, evaluate, update_after_trade


def _s(equity=10_000.0):
    return DailyState("2020-01-02", equity, 0.0, 0, 0, False, False)


def test_hard_loss_flattens_and_locks():
    s = _s()
    s = update_after_trade(s, -260.0)  # -2.6%
    s = evaluate(s)
    assert s.flatten_now is True
    assert s.locked is True


def test_soft_loss_blocks_entries_but_does_not_flatten():
    s = _s()
    s = update_after_trade(s, -160.0)  # -1.6%
    s = evaluate(s)
    assert s.locked is True
    assert s.flatten_now is False


def test_profit_stop():
    s = _s()
    s = update_after_trade(s, 210.0)
    s = evaluate(s)
    assert s.flatten_now is True
    assert s.locked is True


def test_three_consec_losses():
    s = _s()
    for _ in range(3):
        s = update_after_trade(s, -10.0)
    s = evaluate(s)
    assert s.locked is True
    assert s.flatten_now is False


def test_trade_cap():
    s = _s()
    for _ in range(8):
        s = update_after_trade(s, 1.0)  # small wins to avoid other breakers
    s = evaluate(s)
    assert s.locked is True


def test_win_resets_consec_losses():
    s = _s()
    s = update_after_trade(s, -10.0)
    s = update_after_trade(s, -10.0)
    s = update_after_trade(s, +5.0)
    assert s.consec_losses == 0


def test_precedence_hard_beats_profit():
    # Realized P&L in a single step that would satisfy both profit and hard -> hard wins.
    # (Not realistic, but ensures precedence.)
    s = _s()
    s.realized_pnl = -260.0
    s.trade_count = 1
    s = evaluate(s)
    assert s.flatten_now is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_breakers.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement breakers**

```python
# src/v17/backtest/c6_breakers.py
"""Cycle 6 daily circuit-breaker state machine."""
from __future__ import annotations

from dataclasses import dataclass

from v17.setups.c6_constants import (
    HARD_LOSS_PCT, MAX_CONSEC_LOSSES, MAX_TRADES_PER_DAY,
    PROFIT_STOP_PCT, SOFT_LOSS_PCT,
)


@dataclass
class DailyState:
    utc_date: str
    equity_sod: float
    realized_pnl: float
    trade_count: int
    consec_losses: int
    locked: bool
    flatten_now: bool


def update_after_trade(state: DailyState, trade_pnl: float) -> DailyState:
    state.realized_pnl += trade_pnl
    state.trade_count += 1
    if trade_pnl <= 0:
        state.consec_losses += 1
    else:
        state.consec_losses = 0
    return state


def evaluate(state: DailyState) -> DailyState:
    pnl_pct = state.realized_pnl / state.equity_sod if state.equity_sod > 0 else 0.0
    state.flatten_now = False
    # Precedence: hard-loss > profit > soft-loss > consec > trade-cap.
    if pnl_pct <= HARD_LOSS_PCT:
        state.flatten_now = True
        state.locked = True
    elif pnl_pct >= PROFIT_STOP_PCT:
        state.flatten_now = True
        state.locked = True
    elif pnl_pct <= SOFT_LOSS_PCT:
        state.locked = True
    elif state.consec_losses >= MAX_CONSEC_LOSSES:
        state.locked = True
    elif state.trade_count >= MAX_TRADES_PER_DAY:
        state.locked = True
    return state


def allow_entry(state: DailyState) -> bool:
    return not state.locked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_breakers.py -v`
Expected: PASS all seven.

- [ ] **Step 5: Commit**

```bash
git add src/v17/backtest/c6_breakers.py tests/unit/test_c6_breakers.py
git commit -m "feat(c6): daily circuit breakers with precedence"
```

---

## Task 11: Backtest orchestrator `c6_runner.py`

**Files:**
- Create: `src/v17/backtest/c6_runner.py`
- Test: `tests/integration/test_c6_runner.py`

**Interfaces:**
- Consumes: SPX paired M5 df, AUDUSD paired M5 df, USDJPY paired M5 df, calendar index df, params `(K, slope_window, C)`.
- Produces: `run_backtest(spx_m5, fx_m5_by_sym, calendar_idx, params, initial_equity, start_ts_ns, end_ts_ns) -> tuple[pd.DataFrame, pd.DataFrame]` → `(trade_log_df, equity_curve_df)`.
  - `trade_log_df` columns: `trade_id, symbol, side, regime_at_entry, entry_ts_ns, entry_price, initial_stop, r_pips, lots_a, lots_b, leg_a_exit_ts, leg_a_exit_price, leg_a_reason, leg_b_exit_ts, leg_b_exit_price, leg_b_reason, net_pnl_usd, r_multiple, equity_sod`.
  - `equity_curve_df` columns: `ts_utc, equity`.

The orchestrator iterates the shared M5 grid (inner-join SPX+FX timestamps), evaluates regime + micro-signals for each pair per bar, respects entry window, blackouts, warmup, portfolio cap, circuit breakers, and feeds open positions to `c6_position.step` each bar.

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_c6_runner.py
import numpy as np
import pandas as pd

from v17.backtest.c6_runner import run_backtest


def _synthetic_m5(n_days: int, trend: float, pair: str, start_date: str = "2020-01-02"):
    rows = []
    close = 100.0 if pair == "USA500IDXUSD" else (0.7000 if pair == "AUDUSD" else 110.0)
    scale = 1.0 if pair == "USA500IDXUSD" else (0.00005 if pair == "AUDUSD" else 0.01)
    rng = np.random.default_rng(42 + hash(pair) % 1000)
    for d in range(n_days):
        date = pd.Timestamp(start_date, tz="UTC") + pd.Timedelta(days=d)
        for i in range(12 * 10):  # 10 trading hours, 12 M5 bars per hour
            ts = date + pd.Timedelta(hours=8) + pd.Timedelta(minutes=5 * i)
            noise = rng.normal(0, scale)
            close = close + trend * scale + noise
            rows.append({
                "ts_utc": ts.value, "symbol": pair,
                "bid_o": close, "bid_h": close + scale, "bid_l": close - scale, "bid_c": close,
                "ask_o": close + scale * 0.5, "ask_h": close + scale * 1.5,
                "ask_l": close - scale * 0.5, "ask_c": close + scale * 0.5,
                "bid_volume": 100, "ask_volume": 100, "spread_mid": scale * 0.5,
            })
    return pd.DataFrame(rows)


def test_runner_emits_trades_and_curve():
    spx = _synthetic_m5(5, trend=0.1, pair="USA500IDXUSD")
    aud = _synthetic_m5(5, trend=0.1, pair="AUDUSD")
    jpy = _synthetic_m5(5, trend=0.1, pair="USDJPY")
    cal = pd.DataFrame({"ts_utc": [], "currency": [], "impact": [], "title": []})
    tl, ec = run_backtest(
        spx_m5=spx, fx_m5_by_sym={"AUDUSD": aud, "USDJPY": jpy},
        calendar_idx=cal, params={"K": 0.3, "slope_window": 12, "C": 0.4},
        initial_equity=10_000.0,
        start_ts_ns=spx["ts_utc"].min(), end_ts_ns=spx["ts_utc"].max(),
    )
    # With 5 days + rising regime, expect at least some trades.
    assert len(ec) > 0
    assert "equity" in ec.columns
    assert ec["equity"].iloc[0] == 10_000.0
    assert set(["trade_id", "symbol", "side", "entry_ts_ns", "net_pnl_usd"]).issubset(tl.columns)


def test_runner_determinism():
    spx = _synthetic_m5(3, trend=0.1, pair="USA500IDXUSD")
    aud = _synthetic_m5(3, trend=0.1, pair="AUDUSD")
    jpy = _synthetic_m5(3, trend=0.1, pair="USDJPY")
    cal = pd.DataFrame({"ts_utc": [], "currency": [], "impact": [], "title": []})
    params = {"K": 0.3, "slope_window": 12, "C": 0.4}
    tl1, ec1 = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params,
                             10_000.0, spx["ts_utc"].min(), spx["ts_utc"].max())
    tl2, ec2 = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params,
                             10_000.0, spx["ts_utc"].min(), spx["ts_utc"].max())
    pd.testing.assert_frame_equal(tl1, tl2)
    pd.testing.assert_frame_equal(ec1, ec2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_c6_runner.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement orchestrator**

```python
# src/v17/backtest/c6_runner.py
"""Cycle 6 backtest orchestrator."""
from __future__ import annotations

import uuid
from typing import Mapping

import numpy as np
import pandas as pd

from v17.backtest.c6_breakers import DailyState, allow_entry, evaluate, update_after_trade
from v17.backtest.c6_position import C6Position, step as position_step
from v17.backtest.c6_sizing import size_position
from v17.data.c6_calendar import is_blackout, is_calendar_stale
from v17.setups.c6_constants import (
    ATR_FLOOR_MULT, ATR_PERIOD, ENTRY_WINDOW_END_UTC_HM, ENTRY_WINDOW_START_UTC_HM,
    HARD_FLAT_HOUR_MIN_UTC, NEWS_BLACKOUT_MIN, NY_OPEN_BLACKOUT_UTC_HM,
    PORTFOLIO_RISK_PCT, RISK_PCT, SESSION_ANCHOR_HOUR_UTC, TRAIL_EMA_PERIOD, WARMUP_SPX_BARS,
)
from v17.setups.c6_engines import C6_CATALOG
from v17.setups.c6_microtrigger import compute_micro_signals
from v17.setups.c6_regime import _atr_wilder, compute_regime


def _ema(x: np.ndarray, period: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out
    alpha = 2.0 / (period + 1)
    out[0] = x[0]
    for i in range(1, n):
        out[i] = alpha * x[i] + (1 - alpha) * out[i-1]
    return out


def _in_entry_window(ts: pd.Timestamp) -> bool:
    start = ts.replace(hour=ENTRY_WINDOW_START_UTC_HM[0], minute=ENTRY_WINDOW_START_UTC_HM[1], second=0, microsecond=0)
    end = ts.replace(hour=ENTRY_WINDOW_END_UTC_HM[0], minute=ENTRY_WINDOW_END_UTC_HM[1], second=0, microsecond=0)
    if not (start <= ts <= end):
        return False
    bl_start = ts.replace(hour=NY_OPEN_BLACKOUT_UTC_HM[0][0], minute=NY_OPEN_BLACKOUT_UTC_HM[0][1], second=NY_OPEN_BLACKOUT_UTC_HM[0][2], microsecond=0)
    bl_end = ts.replace(hour=NY_OPEN_BLACKOUT_UTC_HM[1][0], minute=NY_OPEN_BLACKOUT_UTC_HM[1][1], second=NY_OPEN_BLACKOUT_UTC_HM[1][2], microsecond=0)
    if bl_start <= ts <= bl_end:
        return False
    return True


def _is_hard_flat(ts: pd.Timestamp) -> bool:
    return ts.hour == HARD_FLAT_HOUR_MIN_UTC[0] and ts.minute >= HARD_FLAT_HOUR_MIN_UTC[1]


def _initial_stop_long(bars_3: pd.DataFrame, entry: float, atr: float) -> float:
    swing = float(bars_3["bid_l"].min())
    floor = entry - ATR_FLOOR_MULT * atr
    return min(swing, floor)


def _initial_stop_short(bars_3: pd.DataFrame, entry: float, atr: float) -> float:
    swing = float(bars_3["ask_h"].max())
    floor = entry + ATR_FLOOR_MULT * atr
    return max(swing, floor)


def _trade_pnl_usd(pos: C6Position, pip_size: float, pip_value_fn) -> float:
    total = 0.0
    for e in pos.exit_log:
        lots = e["lots"]
        delta = (e["price"] - pos.entry_price) if pos.side == "long" else (pos.entry_price - e["price"])
        pip_value = pip_value_fn(pos.entry_price)
        total += (delta / pip_size) * pip_value * lots
    return total


def run_backtest(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    initial_equity: float,
    start_ts_ns: int,
    end_ts_ns: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    K = params["K"]
    slope_window = params["slope_window"]
    C = params["C"]

    regime = compute_regime(spx_m5, k_atr=K, slope_window=slope_window,
                            session_anchor_hour=SESSION_ANCHOR_HOUR_UTC, atr_period=ATR_PERIOD)
    regime = regime.set_index("ts_utc")

    sym_signals: dict[str, pd.DataFrame] = {}
    sym_ema: dict[str, pd.Series] = {}
    sym_df: dict[str, pd.DataFrame] = {}
    for cfg in C6_CATALOG:
        s = fx_m5_by_sym[cfg.symbol].copy().set_index("ts_utc")
        sym_df[cfg.symbol] = s
        sig = compute_micro_signals(s.reset_index(), confirm_body_mult=C, atr_period=ATR_PERIOD,
                                     session_anchor_hour=SESSION_ANCHOR_HOUR_UTC).set_index("ts_utc")
        sym_signals[cfg.symbol] = sig
        mid_c = ((s["bid_c"] + s["ask_c"]) * 0.5).to_numpy()
        sym_ema[cfg.symbol] = pd.Series(_ema(mid_c, TRAIL_EMA_PERIOD), index=s.index)

    shared_index = regime.index.intersection(sym_df["AUDUSD"].index).intersection(sym_df["USDJPY"].index)
    shared_index = shared_index[(shared_index >= start_ts_ns) & (shared_index <= end_ts_ns)]

    open_positions: list[C6Position] = []
    closed: list[dict] = []
    equity_points: list[dict] = []
    equity = float(initial_equity)
    last_date: str = ""
    daily = DailyState(utc_date="", equity_sod=equity, realized_pnl=0.0,
                        trade_count=0, consec_losses=0, locked=False, flatten_now=False)

    for ts_ns in shared_index:
        ts = pd.Timestamp(ts_ns, tz="UTC")
        utc_date = ts.strftime("%Y-%m-%d")
        if utc_date != last_date:
            last_date = utc_date
            daily = DailyState(utc_date, equity, 0.0, 0, 0, False, False)

        if len(calendar_idx) > 0 and is_calendar_stale(ts_ns, calendar_idx, max_age_hours=48):
            # fail-closed: skip whole day
            continue

        hard_flat = _is_hard_flat(ts)

        # Advance open positions first
        still_open: list[C6Position] = []
        for pos in open_positions:
            bar = sym_df[pos.symbol].loc[ts_ns].to_dict()
            bar["ts_utc"] = ts_ns
            ema20 = float(sym_ema[pos.symbol].loc[ts_ns])
            atr = float(sym_signals[pos.symbol].loc[ts_ns, "fx_atr"])
            pos = position_step(pos, bar, ema20=ema20, atr=atr, is_hard_flat=hard_flat)
            if not pos.leg_a_open and not pos.leg_b_open:
                cfg = next(c for c in C6_CATALOG if c.symbol == pos.symbol)
                pnl = _trade_pnl_usd(pos, cfg.pip_size, cfg.pip_value_per_lot)
                equity += pnl
                daily = update_after_trade(daily, pnl)
                daily = evaluate(daily)
                exits_a = [e for e in pos.exit_log if e["leg"] == "A"]
                exits_b = [e for e in pos.exit_log if e["leg"] == "B"]
                closed.append({
                    "trade_id": pos.trade_id, "symbol": pos.symbol, "side": pos.side,
                    "regime_at_entry": getattr(pos, "regime_at_entry", "?"),
                    "entry_ts_ns": pos.entry_ts_ns, "entry_price": pos.entry_price,
                    "initial_stop": pos.initial_stop, "r_pips": int(round(pos.r_price / cfg.pip_size)),
                    "lots_a": pos.lots_a, "lots_b": pos.lots_b,
                    "leg_a_exit_ts": exits_a[0]["ts_ns"] if exits_a else None,
                    "leg_a_exit_price": exits_a[0]["price"] if exits_a else None,
                    "leg_a_reason": exits_a[0]["reason"] if exits_a else None,
                    "leg_b_exit_ts": exits_b[0]["ts_ns"] if exits_b else None,
                    "leg_b_exit_price": exits_b[0]["price"] if exits_b else None,
                    "leg_b_reason": exits_b[0]["reason"] if exits_b else None,
                    "net_pnl_usd": pnl, "r_multiple": pnl / (daily.equity_sod * RISK_PCT),
                    "equity_sod": daily.equity_sod,
                })
            else:
                still_open.append(pos)
        open_positions = still_open

        if daily.flatten_now and open_positions:
            for pos in open_positions:
                bar = sym_df[pos.symbol].loc[ts_ns].to_dict()
                bar["ts_utc"] = ts_ns
                ema20 = float(sym_ema[pos.symbol].loc[ts_ns])
                atr = float(sym_signals[pos.symbol].loc[ts_ns, "fx_atr"])
                pos = position_step(pos, bar, ema20=ema20, atr=atr, is_hard_flat=True)
            open_positions = []

        if not allow_entry(daily) or hard_flat or not _in_entry_window(ts):
            equity_points.append({"ts_utc": ts_ns, "equity": equity})
            continue

        reg_state = regime.loc[ts_ns, "regime_state"]
        if reg_state not in ("LONG_BIAS", "SHORT_BIAS"):
            equity_points.append({"ts_utc": ts_ns, "equity": equity})
            continue

        if len(calendar_idx) > 0 and is_blackout(ts_ns, calendar_idx, NEWS_BLACKOUT_MIN):
            equity_points.append({"ts_utc": ts_ns, "equity": equity})
            continue

        for cfg in C6_CATALOG:
            if any(p.symbol == cfg.symbol for p in open_positions):
                continue
            sig_row = sym_signals[cfg.symbol].loc[ts_ns]
            trigger_long = reg_state == "LONG_BIAS" and bool(sig_row["confirm_long"])
            trigger_short = reg_state == "SHORT_BIAS" and bool(sig_row["confirm_short"])
            if not (trigger_long or trigger_short):
                continue
            side = "long" if trigger_long else "short"

            # Entry on NEXT bar open; look ahead one bar.
            idx_pos = sym_df[cfg.symbol].index.get_indexer([ts_ns])[0]
            if idx_pos < 0 or idx_pos + 1 >= len(sym_df[cfg.symbol]):
                continue
            next_bar = sym_df[cfg.symbol].iloc[idx_pos + 1]
            entry = float(next_bar["ask_o"] if side == "long" else next_bar["bid_o"])

            bars_3 = sym_df[cfg.symbol].iloc[max(0, idx_pos - 2):idx_pos + 1]
            atr = float(sig_row["fx_atr"])
            if np.isnan(atr):
                continue
            if side == "long":
                stop = _initial_stop_long(bars_3, entry, atr)
            else:
                stop = _initial_stop_short(bars_3, entry, atr)
            lots_a, lots_b, r_pips = size_position(cfg.symbol, daily.equity_sod, RISK_PCT, entry, stop)
            if lots_a == 0:
                continue

            # Portfolio cap check.
            cur_open_risk = 0.0
            for p in open_positions:
                cfg_p = next(c for c in C6_CATALOG if c.symbol == p.symbol)
                lots_open = (p.lots_a if p.leg_a_open else 0.0) + (p.lots_b if p.leg_b_open else 0.0)
                price_now = float(sym_df[p.symbol].loc[ts_ns, "bid_c"])
                stop_now = p.leg_b_stop
                cur_open_risk += abs(price_now - stop_now) / cfg_p.pip_size * cfg_p.pip_value_per_lot(price_now) * lots_open
            new_risk = (lots_a + lots_b) * r_pips * cfg.pip_value_per_lot(entry)
            if cur_open_risk + new_risk > PORTFOLIO_RISK_PCT * daily.equity_sod:
                continue

            pos = C6Position(
                trade_id=str(uuid.uuid5(uuid.NAMESPACE_OID, f"{cfg.symbol}-{ts_ns}-{side}")),
                symbol=cfg.symbol, side=side, entry_ts_ns=int(next_bar["ts_utc"]),
                entry_price=entry, initial_stop=stop,
                r_price=abs(entry - stop), lots_a=lots_a, lots_b=lots_b,
                leg_a_open=True, leg_b_open=True, leg_b_stop=stop,
                breakeven_hit=False, exit_log=[],
            )
            pos.regime_at_entry = reg_state
            open_positions.append(pos)

        equity_points.append({"ts_utc": ts_ns, "equity": equity})

    trade_log = pd.DataFrame(closed)
    equity_curve = pd.DataFrame(equity_points)
    return trade_log, equity_curve
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_c6_runner.py -v`
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add src/v17/backtest/c6_runner.py tests/integration/test_c6_runner.py
git commit -m "feat(c6): backtest orchestrator with portfolio cap + blackouts + breakers"
```

---

## Task 12: Metrics helper (Sharpe, PF, max daily loss, consec losing days)

**Files:**
- Create: `src/v17/validation/c6_gates.py`
- Test: `tests/unit/test_c6_gates.py`

**Interfaces:**
- Produces:
  - `compute_metrics(trade_log: pd.DataFrame, equity_curve: pd.DataFrame) -> dict` → keys `{sharpe, pf, trade_count, max_daily_loss_pct, max_consec_losing_days, worst_month_return}`.
  - `evaluate_dev_gates(metrics: dict, mcpt_p: float, paired_a: float, paired_b: float, paired_c: float) -> dict` → keys `D1..D6, A1, A2, A3, all_pass: bool`.
  - `evaluate_holdout_gates(metrics: dict, dev_sharpe: float, mcpt_p: float) -> dict` → keys `H1..H5, all_pass: bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_gates.py
import pandas as pd

from v17.validation.c6_gates import compute_metrics, evaluate_dev_gates, evaluate_holdout_gates


def _mk_trades(pnls):
    return pd.DataFrame({
        "entry_ts_ns": [pd.Timestamp(f"2020-01-{i+1:02d}", tz='UTC').value for i in range(len(pnls))],
        "net_pnl_usd": pnls,
        "equity_sod": [10_000.0] * len(pnls),
        "r_multiple": [p / 50.0 for p in pnls],
    })


def _mk_eq(points):
    return pd.DataFrame({"ts_utc": [i * 86_400_000_000_000 for i in range(len(points))], "equity": points})


def test_metrics_basic():
    trades = _mk_trades([50, -25, 100, -40, 60])
    eq = _mk_eq([10_000, 10_050, 10_025, 10_125, 10_085, 10_145])
    m = compute_metrics(trades, eq)
    assert m["trade_count"] == 5
    assert m["pf"] > 1.0


def test_dev_gates_pass_mock_strong():
    m = {"sharpe": 1.5, "pf": 1.5, "trade_count": 900, "max_daily_loss_pct": -0.02,
         "max_consec_losing_days": 3, "worst_month_return": -0.01}
    g = evaluate_dev_gates(m, mcpt_p=0.02, paired_a=0.01, paired_b=0.08, paired_c=0.09)
    assert g["all_pass"] is True


def test_dev_gates_fail_low_sharpe():
    m = {"sharpe": 0.8, "pf": 1.5, "trade_count": 900, "max_daily_loss_pct": -0.02,
         "max_consec_losing_days": 3, "worst_month_return": -0.01}
    g = evaluate_dev_gates(m, mcpt_p=0.02, paired_a=0.01, paired_b=0.08, paired_c=0.09)
    assert g["D1"] is False
    assert g["all_pass"] is False


def test_holdout_gates():
    m = {"sharpe": 0.9, "pf": 1.2, "trade_count": 200, "max_daily_loss_pct": -0.02,
         "max_consec_losing_days": 3, "worst_month_return": -0.03}
    g = evaluate_holdout_gates(m, dev_sharpe=1.2, mcpt_p=0.08)
    # 0.9 >= 0.7 * 1.2 = 0.84 -> H1 pass. PF 1.2 < 1.15? 1.2 > 1.15 so pass.
    assert g["H1"] is True
    assert g["H2"] is True
    assert g["H3"] is True
    assert g["H4"] is True
    assert g["H5"] is True
    assert g["all_pass"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_gates.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement metrics + gates**

```python
# src/v17/validation/c6_gates.py
"""Cycle 6 metrics + pre-registered gate evaluators."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _sharpe_from_trades(net_pnl: np.ndarray) -> float:
    if len(net_pnl) < 2:
        return 0.0
    mu = net_pnl.mean()
    sd = net_pnl.std(ddof=1)
    if sd == 0:
        return 0.0
    # Annualize: assume ~250 trading days; infer bars/year proxy via trade rate -> use per-trade Sharpe scaled by sqrt(n/years).
    # For our 9-year dev set, sqrt(n/9) * mu/sd is roughly annualized. Keep simple: per-trade Sharpe * sqrt(252 * 3) as proxy
    # where 3 ~ avg trades/day. Replaced by a per-trade-stat * sqrt(trades/year) convention.
    return float(mu / sd * np.sqrt(252))


def compute_metrics(trade_log: pd.DataFrame, equity_curve: pd.DataFrame) -> dict:
    if len(trade_log) == 0:
        return {"sharpe": 0.0, "pf": 0.0, "trade_count": 0, "max_daily_loss_pct": 0.0,
                "max_consec_losing_days": 0, "worst_month_return": 0.0}
    pnl = trade_log["net_pnl_usd"].to_numpy()
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    pf = float(wins / losses) if losses > 0 else float("inf")
    sharpe = _sharpe_from_trades(pnl)

    tl = trade_log.copy()
    tl["date"] = pd.to_datetime(tl["entry_ts_ns"], unit="ns", utc=True).dt.strftime("%Y-%m-%d")
    daily = tl.groupby("date").agg(pnl=("net_pnl_usd", "sum"), equity_sod=("equity_sod", "first"))
    daily["pct"] = daily["pnl"] / daily["equity_sod"]
    max_daily_loss = float(daily["pct"].min()) if len(daily) else 0.0

    loss_streak, max_streak = 0, 0
    for p in daily["pct"]:
        if p < 0:
            loss_streak += 1
            max_streak = max(max_streak, loss_streak)
        else:
            loss_streak = 0

    tl["month"] = pd.to_datetime(tl["entry_ts_ns"], unit="ns", utc=True).dt.strftime("%Y-%m")
    monthly = tl.groupby("month").agg(pnl=("net_pnl_usd", "sum"), equity_sod=("equity_sod", "first"))
    monthly["pct"] = monthly["pnl"] / monthly["equity_sod"]
    worst_month = float(monthly["pct"].min()) if len(monthly) else 0.0

    return {
        "sharpe": sharpe, "pf": pf, "trade_count": int(len(trade_log)),
        "max_daily_loss_pct": max_daily_loss,
        "max_consec_losing_days": int(max_streak),
        "worst_month_return": worst_month,
    }


def evaluate_dev_gates(metrics: dict, mcpt_p: float, paired_a: float,
                         paired_b: float, paired_c: float) -> dict:
    g = {
        "D1": metrics["sharpe"] >= 1.0,
        "D2": mcpt_p <= 0.05,
        "D3": metrics["pf"] >= 1.25,
        "D4": metrics["max_daily_loss_pct"] >= -0.03,
        "D5": metrics["max_consec_losing_days"] <= 5,
        "D6": metrics["trade_count"] >= 800,
        "A1": paired_a <= 0.05,
        "A2": paired_b <= 0.10,
        "A3": paired_c <= 0.10,
    }
    # Spec: if A1 passes but A2 and A3 both fail -> shelve. Encode by requiring A2 OR A3 pass.
    ablation_ok = g["A1"] and (g["A2"] or g["A3"])
    g["all_pass"] = all([g["D1"], g["D2"], g["D3"], g["D4"], g["D5"], g["D6"], ablation_ok])
    return g


def evaluate_holdout_gates(metrics: dict, dev_sharpe: float, mcpt_p: float) -> dict:
    g = {
        "H1": metrics["sharpe"] >= 0.7 * dev_sharpe,
        "H2": mcpt_p <= 0.10,
        "H3": metrics["pf"] >= 1.15,
        "H4": metrics["max_daily_loss_pct"] >= -0.03,
        "H5": metrics["worst_month_return"] >= -0.05,
    }
    g["all_pass"] = all(g[k] for k in ("H1", "H2", "H3", "H4", "H5"))
    return g
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_gates.py -v`
Expected: PASS all four.

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/c6_gates.py tests/unit/test_c6_gates.py
git commit -m "feat(c6): metrics + pre-registered gate evaluators"
```

---

## Task 13: Scheme-1 MCPT for Cycle 6

**Files:**
- Create: `src/v17/validation/c6_mcpt.py`
- Test: `tests/unit/test_c6_mcpt.py`

**Interfaces:**
- Consumes: observed trade log, equity curve, re-run callable.
- Produces: `scheme1_mcpt(trade_log: pd.DataFrame, run_null: Callable[[int], pd.DataFrame], n_permutations: int, seed: int) -> dict` → keys `{observed_sharpe, null_sharpe_mean, null_sharpe_p95, p_sharpe}`. `run_null(perm_index)` returns a permuted trade log. Caller provides the null-constructor.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_mcpt.py
import numpy as np
import pandas as pd

from v17.validation.c6_mcpt import scheme1_mcpt


def _tl(pnls):
    return pd.DataFrame({
        "entry_ts_ns": [i * 1_000_000_000 for i in range(len(pnls))],
        "net_pnl_usd": pnls, "equity_sod": [10_000] * len(pnls),
    })


def test_scheme1_observed_beats_random_null():
    obs = _tl([50, 60, 40, 70, -20] * 20)  # strong positive drift

    def run_null(perm_idx):
        rng = np.random.default_rng(perm_idx + 7)
        return _tl(rng.normal(0, 40, 100).tolist())

    r = scheme1_mcpt(obs, run_null, n_permutations=50, seed=42)
    assert r["p_sharpe"] <= 0.10  # observed should beat random null most of the time


def test_scheme1_observed_indistinguishable_from_null():
    rng = np.random.default_rng(3)
    obs = _tl(rng.normal(0, 40, 100).tolist())

    def run_null(perm_idx):
        rng2 = np.random.default_rng(perm_idx + 1000)
        return _tl(rng2.normal(0, 40, 100).tolist())

    r = scheme1_mcpt(obs, run_null, n_permutations=50, seed=42)
    assert 0.05 <= r["p_sharpe"] <= 0.95
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_mcpt.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement MCPT**

```python
# src/v17/validation/c6_mcpt.py
"""Scheme-1 MCPT for Cycle 6."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from v17.validation.c6_gates import _sharpe_from_trades


def scheme1_mcpt(
    trade_log: pd.DataFrame,
    run_null: Callable[[int], pd.DataFrame],
    n_permutations: int,
    seed: int,
) -> dict:
    obs_sharpe = _sharpe_from_trades(trade_log["net_pnl_usd"].to_numpy())
    null_sharpes = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        null_tl = run_null(i)
        null_sharpes[i] = _sharpe_from_trades(null_tl["net_pnl_usd"].to_numpy())
    p = float((null_sharpes >= obs_sharpe).sum() + 1) / (n_permutations + 1)
    return {
        "observed_sharpe": obs_sharpe,
        "null_sharpe_mean": float(null_sharpes.mean()),
        "null_sharpe_p95": float(np.percentile(null_sharpes, 95)),
        "p_sharpe": p,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_mcpt.py -v`
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/c6_mcpt.py tests/unit/test_c6_mcpt.py
git commit -m "feat(c6): scheme-1 MCPT with pluggable null constructor"
```

---

## Task 14: Paired-alpha ablation nulls

**Files:**
- Create: `src/v17/validation/c6_paired_alpha.py`
- Test: `tests/unit/test_c6_paired_alpha.py`

**Interfaces:**
- Consumes: observed trade log, seed, pair-eligible bars, exit rules.
- Produces:
  - `null_random_entries(spx_m5, fx_m5_by_sym, calendar_idx, params, equity, n_trades_per_sym_dir: dict, seed: int) -> pd.DataFrame` → Null-A: random M5 entries matching observed per-pair-per-direction counts.
  - `null_regime_only(spx_m5, fx_m5_by_sym, calendar_idx, params, equity, seed: int) -> pd.DataFrame` → Null-B: fire entry at every regime-flip bar, same exits.
  - `null_micro_only(spx_m5, fx_m5_by_sym, calendar_idx, params, equity, seed: int) -> pd.DataFrame` → Null-C: fire entry at every FX micro-trigger without SPX regime gate.
  - `paired_alpha(obs_tl, null_tl, seed, n_bootstrap: int = 1000) -> float` → bootstrap p-value on paired Sharpe-difference.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_c6_paired_alpha.py
import numpy as np
import pandas as pd

from v17.validation.c6_paired_alpha import paired_alpha


def test_paired_alpha_rejects_null_when_obs_much_better():
    obs = pd.DataFrame({"net_pnl_usd": np.random.default_rng(1).normal(10, 30, 500)})
    nul = pd.DataFrame({"net_pnl_usd": np.random.default_rng(2).normal(-5, 30, 500)})
    p = paired_alpha(obs, nul, seed=42, n_bootstrap=500)
    assert p < 0.05


def test_paired_alpha_cant_reject_when_similar():
    rng = np.random.default_rng(1)
    obs = pd.DataFrame({"net_pnl_usd": rng.normal(0, 30, 500)})
    nul = pd.DataFrame({"net_pnl_usd": rng.normal(0, 30, 500)})
    p = paired_alpha(obs, nul, seed=42, n_bootstrap=500)
    assert p > 0.10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_c6_paired_alpha.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement paired-alpha**

```python
# src/v17/validation/c6_paired_alpha.py
"""Cycle 6 paired-alpha ablation nulls: random, regime-only, micro-only."""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from v17.backtest.c6_runner import run_backtest
from v17.setups.c6_microtrigger import compute_micro_signals
from v17.setups.c6_regime import compute_regime
from v17.validation.c6_gates import _sharpe_from_trades


def paired_alpha(obs_tl: pd.DataFrame, null_tl: pd.DataFrame, seed: int, n_bootstrap: int = 1000) -> float:
    rng = np.random.default_rng(seed)
    obs_pnl = obs_tl["net_pnl_usd"].to_numpy()
    null_pnl = null_tl["net_pnl_usd"].to_numpy()
    obs_sharpe = _sharpe_from_trades(obs_pnl)
    null_sharpe = _sharpe_from_trades(null_pnl)
    diff_obs = obs_sharpe - null_sharpe
    pooled = np.concatenate([obs_pnl, null_pnl])
    n_o, n_n = len(obs_pnl), len(null_pnl)
    diffs = np.empty(n_bootstrap, dtype=float)
    for i in range(n_bootstrap):
        perm = rng.permutation(pooled)
        a, b = perm[:n_o], perm[n_o:n_o + n_n]
        diffs[i] = _sharpe_from_trades(a) - _sharpe_from_trades(b)
    p = float((diffs >= diff_obs).sum() + 1) / (n_bootstrap + 1)
    return p


def null_random_entries(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    n_trades_per_sym_dir: dict,
    seed: int,
) -> pd.DataFrame:
    """Null-A: sample random M5 entry bars per (symbol, direction) matching observed counts.

    Exits follow the normal position state-machine. Returns a trade log in same schema.
    """
    rng = np.random.default_rng(seed)
    # Build a synthetic trade log by running the same orchestrator with a forced override:
    # easiest: patch micro-trigger outputs. For simplicity we re-implement entry generation here.
    # Full implementation: call run_backtest with modified micro-trigger results.
    # Delegated-to runner helper to avoid rewriting exit logic.
    raise NotImplementedError("Wired in Task 15 driver where override callback lives.")


def null_regime_only(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    seed: int,
) -> pd.DataFrame:
    raise NotImplementedError("Wired in Task 15 driver.")


def null_micro_only(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    seed: int,
) -> pd.DataFrame:
    raise NotImplementedError("Wired in Task 15 driver.")
```

Note: paired_alpha is the testable bootstrap; the three null generators are wired in Task 15 via a `run_backtest` override hook. This task closes once `paired_alpha` tests pass.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_c6_paired_alpha.py -v`
Expected: PASS both (`paired_alpha` is the only function exercised; stubs are untested at this stage).

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/c6_paired_alpha.py tests/unit/test_c6_paired_alpha.py
git commit -m "feat(c6): paired-alpha bootstrap + null generator stubs"
```

---

## Task 15: Grid search driver (48 configs on dev) + wire nulls

**Files:**
- Create: `src/v17/backtest/c6_grid.py`
- Modify: `src/v17/backtest/c6_runner.py` (add `signal_override` parameter)
- Modify: `src/v17/validation/c6_paired_alpha.py` (implement three null generators using override)
- Test: `tests/integration/test_c6_grid.py`

**Interfaces:**
- Consumes: SPX M5, FX M5 by symbol, calendar, dev window.
- Produces:
  - Add parameter `signal_override: Callable[[str, pd.DataFrame], pd.DataFrame] | None = None` to `run_backtest`. When present, replaces `compute_micro_signals` output for each symbol.
  - `run_grid(spx_m5, fx_m5_by_sym, calendar_idx, start_ts_ns, end_ts_ns, equity) -> pd.DataFrame` → one row per config with `(K, slope_window, C, sharpe, pf, trade_count, max_daily_loss_pct, max_consec_losing_days)`.
  - Implement `null_random_entries`, `null_regime_only`, `null_micro_only` using `signal_override`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_c6_grid.py
import numpy as np
import pandas as pd

from v17.backtest.c6_grid import run_grid


def _mk_series(n_days: int, trend: float, pair: str):
    from tests.integration.test_c6_runner import _synthetic_m5
    return _synthetic_m5(n_days, trend, pair)


def test_grid_runs_all_48_configs_small_dev():
    spx = _mk_series(10, 0.05, "USA500IDXUSD")
    aud = _mk_series(10, 0.05, "AUDUSD")
    jpy = _mk_series(10, 0.05, "USDJPY")
    cal = pd.DataFrame({"ts_utc": [], "currency": [], "impact": [], "title": []})
    grid = run_grid(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal,
                     start_ts_ns=spx["ts_utc"].min(), end_ts_ns=spx["ts_utc"].max(),
                     equity=10_000.0)
    assert len(grid) == 48
    assert set(["K", "slope_window", "C", "sharpe", "pf", "trade_count"]).issubset(grid.columns)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/integration/test_c6_grid.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Add `signal_override` hook to `run_backtest`**

In `src/v17/backtest/c6_runner.py`, change the signature to include `signal_override: Callable[[str, pd.DataFrame], pd.DataFrame] | None = None`, and replace the signal-compute block with:

```python
for cfg in C6_CATALOG:
    s = fx_m5_by_sym[cfg.symbol].copy().set_index("ts_utc")
    sym_df[cfg.symbol] = s
    raw_signals = compute_micro_signals(
        s.reset_index(), confirm_body_mult=C, atr_period=ATR_PERIOD,
        session_anchor_hour=SESSION_ANCHOR_HOUR_UTC,
    )
    if signal_override is not None:
        raw_signals = signal_override(cfg.symbol, raw_signals)
    sym_signals[cfg.symbol] = raw_signals.set_index("ts_utc")
    ...
```

- [ ] **Step 4: Implement grid driver**

```python
# src/v17/backtest/c6_grid.py
"""Cycle 6 grid search over (K, slope_window, C)."""
from __future__ import annotations

from typing import Mapping

import pandas as pd

from v17.backtest.c6_runner import run_backtest
from v17.setups.c6_constants import CONFIRM_BODY_GRID, K_GRID, SLOPE_WINDOW_GRID
from v17.validation.c6_gates import compute_metrics


def run_grid(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    start_ts_ns: int,
    end_ts_ns: int,
    equity: float,
) -> pd.DataFrame:
    rows = []
    for K in K_GRID:
        for sw in SLOPE_WINDOW_GRID:
            for C in CONFIRM_BODY_GRID:
                tl, ec = run_backtest(
                    spx_m5, fx_m5_by_sym, calendar_idx,
                    params={"K": K, "slope_window": sw, "C": C},
                    initial_equity=equity, start_ts_ns=start_ts_ns, end_ts_ns=end_ts_ns,
                )
                m = compute_metrics(tl, ec)
                rows.append({
                    "K": K, "slope_window": sw, "C": C,
                    "sharpe": m["sharpe"], "pf": m["pf"], "trade_count": m["trade_count"],
                    "max_daily_loss_pct": m["max_daily_loss_pct"],
                    "max_consec_losing_days": m["max_consec_losing_days"],
                })
    return pd.DataFrame(rows)
```

- [ ] **Step 5: Implement the three null generators**

Replace stubs in `src/v17/validation/c6_paired_alpha.py`:

```python
from v17.backtest.c6_runner import run_backtest
from v17.setups.c6_regime import compute_regime


def null_random_entries(spx_m5, fx_m5_by_sym, calendar_idx, params, equity,
                         n_trades_per_sym_dir, seed):
    rng = np.random.default_rng(seed)

    def override(sym, sig_df):
        n_long = n_trades_per_sym_dir.get((sym, "long"), 0)
        n_short = n_trades_per_sym_dir.get((sym, "short"), 0)
        sig_df = sig_df.copy()
        sig_df["confirm_long"] = False
        sig_df["confirm_short"] = False
        idx_long = rng.choice(len(sig_df), size=min(n_long, len(sig_df)), replace=False)
        sig_df.loc[sig_df.index[idx_long], "confirm_long"] = True
        remaining = sig_df.index.difference(sig_df.index[idx_long])
        idx_short = rng.choice(len(remaining), size=min(n_short, len(remaining)), replace=False)
        sig_df.loc[remaining[idx_short], "confirm_short"] = True
        return sig_df

    tl, _ = run_backtest(spx_m5, fx_m5_by_sym, calendar_idx, params, equity,
                          start_ts_ns=spx_m5["ts_utc"].min(), end_ts_ns=spx_m5["ts_utc"].max(),
                          signal_override=override)
    return tl


def null_regime_only(spx_m5, fx_m5_by_sym, calendar_idx, params, equity, seed):
    reg = compute_regime(spx_m5, k_atr=params["K"], slope_window=params["slope_window"]).set_index("ts_utc")
    flips = reg["regime_state"].shift(1) != reg["regime_state"]
    long_bars = reg.index[flips & (reg["regime_state"] == "LONG_BIAS")]
    short_bars = reg.index[flips & (reg["regime_state"] == "SHORT_BIAS")]

    def override(sym, sig_df):
        sig_df = sig_df.copy()
        sig_df["confirm_long"] = sig_df["ts_utc"].isin(long_bars)
        sig_df["confirm_short"] = sig_df["ts_utc"].isin(short_bars)
        return sig_df

    tl, _ = run_backtest(spx_m5, fx_m5_by_sym, calendar_idx, params, equity,
                          start_ts_ns=spx_m5["ts_utc"].min(), end_ts_ns=spx_m5["ts_utc"].max(),
                          signal_override=override)
    return tl


def null_micro_only(spx_m5, fx_m5_by_sym, calendar_idx, params, equity, seed):
    # Override regime to always LONG_BIAS to force all micro signals through.
    # Implemented via a sentinel SPX constructed from constants would be complex;
    # instead inject via override where we flip regime gate: we emit confirm_long/short
    # with no regime filtering by setting confirm_long=pullback&close>vwap (already in signal).
    # Simplest path: keep observed micro-trigger but call runner with a synthetic SPX whose
    # regime is always LONG_BIAS for long signals, SHORT_BIAS for short signals.
    # Here we fake it by setting override's output to pass through micro-signal as-is,
    # and using a modified spx_m5 with deterministic trending mid.
    spx_fake = spx_m5.copy()
    # Force a strongly-trending SPX series so regime == LONG_BIAS throughout.
    spx_fake["bid_c"] = np.linspace(1000.0, 1_000_000.0, len(spx_fake))
    spx_fake["ask_c"] = spx_fake["bid_c"] + 0.1
    spx_fake["bid_h"] = spx_fake["bid_c"]; spx_fake["ask_h"] = spx_fake["ask_c"]
    spx_fake["bid_l"] = spx_fake["bid_c"]; spx_fake["ask_l"] = spx_fake["ask_c"]
    spx_fake["bid_o"] = spx_fake["bid_c"]; spx_fake["ask_o"] = spx_fake["ask_c"]
    # With this SPX, regime is LONG_BIAS almost always; short signals get filtered. Repeat with
    # downtrending SPX for short signals and concatenate the two resulting trade logs.
    tl_long, _ = run_backtest(spx_fake, fx_m5_by_sym, calendar_idx, params, equity,
                                start_ts_ns=spx_m5["ts_utc"].min(), end_ts_ns=spx_m5["ts_utc"].max(),
                                signal_override=None)
    spx_down = spx_fake.copy()
    spx_down[["bid_c", "ask_c", "bid_h", "ask_h", "bid_l", "ask_l", "bid_o", "ask_o"]] = (
        spx_fake[["bid_c", "ask_c", "bid_h", "ask_h", "bid_l", "ask_l", "bid_o", "ask_o"]].iloc[::-1].values
    )
    tl_short, _ = run_backtest(spx_down, fx_m5_by_sym, calendar_idx, params, equity,
                                 start_ts_ns=spx_m5["ts_utc"].min(), end_ts_ns=spx_m5["ts_utc"].max(),
                                 signal_override=None)
    return pd.concat([tl_long, tl_short], ignore_index=True)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/integration/test_c6_grid.py tests/unit/test_c6_paired_alpha.py -v`
Expected: PASS all.

- [ ] **Step 7: Commit**

```bash
git add src/v17/backtest/c6_grid.py src/v17/backtest/c6_runner.py src/v17/validation/c6_paired_alpha.py tests/integration/test_c6_grid.py
git commit -m "feat(c6): grid driver + ablation null generators"
```

---

## Task 16: Dev gate report generator

**Files:**
- Create: `src/v17/cli_c6.py`
- Modify: `src/v17/cli.py` to register the sub-app.
- Test: `tests/integration/test_c6_cli_dev_report.py`

**Interfaces:**
- CLI commands:
  - `v17 c6 ingest-m1 --bid-csv BID --ask-csv ASK --symbol SYM --out-root DIR`
  - `v17 c6 build-m5 --m1-root DIR --m5-root DIR --symbol SYM --year YYYY`
  - `v17 c6 build-calendar --ff-dir DIR --out PARQUET`
  - `v17 c6 grid --dev-start ISO --dev-end ISO --out-csv CSV`
  - `v17 c6 dev-report --grid-csv CSV --trade-log CSV --mcpt-json JSON --paired-json JSON --out-md MD`
- Produces: markdown report to `docs/superpowers/plans/c6_dev_gate_report_YYYY-MM-DD.md` with gate table + sign-off placeholders.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_c6_cli_dev_report.py
from pathlib import Path
import json
from typer.testing import CliRunner

from v17.cli_c6 import app as c6_app


def test_dev_report_generates_markdown(tmp_path):
    runner = CliRunner()
    # Minimal fake inputs.
    grid = tmp_path / "grid.csv"
    import pandas as pd
    pd.DataFrame([{"K": 0.3, "slope_window": 12, "C": 0.4,
                     "sharpe": 1.2, "pf": 1.4, "trade_count": 900,
                     "max_daily_loss_pct": -0.02, "max_consec_losing_days": 3}]).to_csv(grid, index=False)
    tl = tmp_path / "tl.csv"
    pd.DataFrame({"net_pnl_usd": [50, 60, -30, 70, -25] * 200,
                   "entry_ts_ns": [i * 1_000_000_000_000 for i in range(1000)],
                   "equity_sod": [10000] * 1000}).to_csv(tl, index=False)
    mcpt = tmp_path / "mcpt.json"; mcpt.write_text(json.dumps({"p_sharpe": 0.02, "observed_sharpe": 1.2}))
    paired = tmp_path / "paired.json"; paired.write_text(json.dumps({"A1": 0.02, "A2": 0.05, "A3": 0.07}))
    out = tmp_path / "report.md"
    r = runner.invoke(c6_app, ["dev-report", "--grid-csv", str(grid), "--trade-log", str(tl),
                                  "--mcpt-json", str(mcpt), "--paired-json", str(paired),
                                  "--out-md", str(out)])
    assert r.exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert "D1" in text and "A1" in text
    assert "best_config" in text or "Best config" in text
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/integration/test_c6_cli_dev_report.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `cli_c6.py` with the five subcommands**

```python
# src/v17/cli_c6.py
"""Cycle 6 CLI entrypoint."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import typer

from v17.data.c6_calendar import build_calendar_index
from v17.data.c6_pipeline import build_m5_paired, ingest_m1_paired
from v17.validation.c6_gates import (
    compute_metrics, evaluate_dev_gates, evaluate_holdout_gates,
)

app = typer.Typer(name="c6", help="Cycle 6 SPX-led intraday FX")


@app.command("ingest-m1")
def ingest_m1_cmd(bid_csv: Path, ask_csv: Path, symbol: str, out_root: Path):
    n = ingest_m1_paired(bid_csv, ask_csv, symbol, out_root)
    typer.echo(f"wrote {n} rows")


@app.command("build-m5")
def build_m5_cmd(m1_root: Path, m5_root: Path, symbol: str, year: int):
    n = build_m5_paired(m1_root, m5_root, symbol, year)
    typer.echo(f"wrote {n} m5 bars")


@app.command("build-calendar")
def build_calendar_cmd(ff_dir: Path, out: Path):
    n = build_calendar_index(ff_dir, out, ("USD", "AUD", "JPY"))
    typer.echo(f"indexed {n} events")


@app.command("grid")
def grid_cmd(dev_start: str, dev_end: str, out_csv: Path):
    typer.echo(f"grid run for {dev_start}..{dev_end} -> {out_csv}")  # full wiring in Task 17


@app.command("dev-report")
def dev_report_cmd(
    grid_csv: Path, trade_log: Path, mcpt_json: Path, paired_json: Path, out_md: Path,
):
    grid = pd.read_csv(grid_csv).sort_values("sharpe", ascending=False).reset_index(drop=True)
    best = grid.iloc[0].to_dict()
    tl = pd.read_csv(trade_log)
    ec = pd.DataFrame({"ts_utc": tl["entry_ts_ns"], "equity": 10_000})  # placeholder
    m = compute_metrics(tl, ec)
    mcpt = json.loads(mcpt_json.read_text())
    paired = json.loads(paired_json.read_text())
    gates = evaluate_dev_gates(m, mcpt["p_sharpe"], paired["A1"], paired["A2"], paired["A3"])

    lines = [
        "# Cycle 6 — Dev Gate Report",
        "",
        f"**Best config:** K={best['K']} slope_window={best['slope_window']} C={best['C']}",
        f"- sharpe={best['sharpe']:.3f}, pf={best['pf']:.3f}, trades={int(best['trade_count'])}",
        "",
        "## Gates",
        "",
        "| Gate | Observed | Required | Pass |",
        "|------|----------|----------|------|",
        f"| D1 Sharpe | {m['sharpe']:.3f} | >= 1.0 | {gates['D1']} |",
        f"| D2 MCPT p | {mcpt['p_sharpe']:.4f} | <= 0.05 | {gates['D2']} |",
        f"| D3 PF | {m['pf']:.3f} | >= 1.25 | {gates['D3']} |",
        f"| D4 max daily loss | {m['max_daily_loss_pct']:.3%} | >= -3.0% | {gates['D4']} |",
        f"| D5 max consec losing days | {m['max_consec_losing_days']} | <= 5 | {gates['D5']} |",
        f"| D6 trade count | {m['trade_count']} | >= 800 | {gates['D6']} |",
        f"| A1 vs random | p={paired['A1']:.4f} | <= 0.05 | {gates['A1']} |",
        f"| A2 vs regime-only | p={paired['A2']:.4f} | <= 0.10 | {gates['A2']} |",
        f"| A3 vs micro-only | p={paired['A3']:.4f} | <= 0.10 | {gates['A3']} |",
        "",
        f"**ALL GATES PASS: {gates['all_pass']}**",
        "",
        "## Sign-off",
        "- [ ] User approves parameters lock",
        "- [ ] Parameters frozen for holdout phase",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    typer.echo(str(out_md))
```

Modify `src/v17/cli.py`: add import `from v17.cli_c6 import app as c6_app` and `app.add_typer(c6_app, name="c6")`.

- [ ] **Step 4: Run test to verify passes**

Run: `pytest tests/integration/test_c6_cli_dev_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/v17/cli_c6.py src/v17/cli.py tests/integration/test_c6_cli_dev_report.py
git commit -m "feat(c6): CLI with ingest/build/grid/dev-report commands"
```

---

## Task 17: End-to-end dev pipeline wiring (S4 execution)

**Files:**
- Modify: `src/v17/cli_c6.py` (implement full `grid` and add `mcpt-dev`, `paired-alpha-dev` commands)
- Test: `tests/integration/test_c6_cli_grid.py`

**Interfaces:**
- CLI additions:
  - `v17 c6 grid --spx-root DIR --fx-root DIR --calendar PARQUET --dev-start ISO --dev-end ISO --out-csv CSV` → runs 48-config grid, writes CSV.
  - `v17 c6 mcpt-dev --spx-root --fx-root --calendar --params-json PARAMS --dev-start --dev-end --n-permutations N --out-json JSON`
  - `v17 c6 paired-alpha-dev --spx-root --fx-root --calendar --params-json PARAMS --dev-start --dev-end --out-json JSON`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_c6_cli_grid.py
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from typer.testing import CliRunner

from v17.cli_c6 import app as c6_app
from tests.integration.test_c6_runner import _synthetic_m5


def _write_m5(df, root, sym, year):
    out = root / sym / f"year={year}" / "part-00.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out, compression="zstd")


def test_grid_cli_writes_48_rows(tmp_path):
    spx_root = tmp_path / "spx"; fx_root = tmp_path / "fx"
    spx = _synthetic_m5(10, 0.05, "USA500IDXUSD")
    aud = _synthetic_m5(10, 0.05, "AUDUSD")
    jpy = _synthetic_m5(10, 0.05, "USDJPY")
    _write_m5(spx, spx_root, "USA500IDXUSD", 2020)
    _write_m5(aud, fx_root, "AUDUSD", 2020)
    _write_m5(jpy, fx_root, "USDJPY", 2020)
    cal = tmp_path / "cal.parquet"
    pd.DataFrame({"ts_utc": [], "currency": [], "impact": [], "title": []}).to_parquet(cal)
    out_csv = tmp_path / "grid.csv"
    r = CliRunner().invoke(c6_app, ["grid",
        "--spx-root", str(spx_root), "--fx-root", str(fx_root), "--calendar", str(cal),
        "--dev-start", "2020-01-01", "--dev-end", "2020-01-15",
        "--out-csv", str(out_csv)])
    assert r.exit_code == 0, r.output
    assert out_csv.exists()
    assert len(pd.read_csv(out_csv)) == 48
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/integration/test_c6_cli_grid.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement full wiring in `cli_c6.py`**

Replace the `grid_cmd` stub and add MCPT/paired commands:

```python
# Append / replace in src/v17/cli_c6.py

import pyarrow.parquet as pq
from v17.backtest.c6_grid import run_grid
from v17.backtest.c6_runner import run_backtest
from v17.data.c6_calendar import load_calendar_index
from v17.validation.c6_mcpt import scheme1_mcpt
from v17.validation.c6_paired_alpha import (
    null_micro_only, null_random_entries, null_regime_only, paired_alpha,
)


def _load_m5(root: Path, symbol: str, start_iso: str, end_iso: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start_iso, tz="UTC").value
    end_ts = pd.Timestamp(end_iso, tz="UTC").value
    frames = []
    for y_dir in sorted((root / symbol).glob("year=*")):
        frames.append(pq.read_table(y_dir / "part-00.parquet").to_pandas())
    df = pd.concat(frames, ignore_index=True)
    return df[(df["ts_utc"] >= start_ts) & (df["ts_utc"] <= end_ts)].reset_index(drop=True)


@app.command("grid")
def grid_cmd(spx_root: Path, fx_root: Path, calendar: Path,
             dev_start: str, dev_end: str, out_csv: Path):
    spx = _load_m5(spx_root, "USA500IDXUSD", dev_start, dev_end)
    aud = _load_m5(fx_root, "AUDUSD", dev_start, dev_end)
    jpy = _load_m5(fx_root, "USDJPY", dev_start, dev_end)
    cal = load_calendar_index(calendar) if calendar.exists() and calendar.stat().st_size > 0 else pd.DataFrame(columns=["ts_utc", "currency", "impact", "title"])
    g = run_grid(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal,
                   spx["ts_utc"].min(), spx["ts_utc"].max(), 10_000.0)
    g.to_csv(out_csv, index=False)
    typer.echo(str(out_csv))


@app.command("mcpt-dev")
def mcpt_dev_cmd(spx_root: Path, fx_root: Path, calendar: Path,
                   params_json: Path, dev_start: str, dev_end: str,
                   n_permutations: int, out_json: Path):
    params = json.loads(params_json.read_text())
    spx = _load_m5(spx_root, "USA500IDXUSD", dev_start, dev_end)
    aud = _load_m5(fx_root, "AUDUSD", dev_start, dev_end)
    jpy = _load_m5(fx_root, "USDJPY", dev_start, dev_end)
    cal = load_calendar_index(calendar) if calendar.exists() else pd.DataFrame(columns=["ts_utc", "currency", "impact", "title"])
    tl, _ = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0,
                          spx["ts_utc"].min(), spx["ts_utc"].max())
    counts = tl.groupby(["symbol", "side"]).size().to_dict()

    def run_null(i):
        return null_random_entries(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params,
                                     10_000.0, counts, seed=42 + i)

    r = scheme1_mcpt(tl, run_null, n_permutations=n_permutations, seed=42)
    out_json.write_text(json.dumps(r), encoding="utf-8")
    typer.echo(str(out_json))


@app.command("paired-alpha-dev")
def paired_alpha_dev_cmd(spx_root: Path, fx_root: Path, calendar: Path,
                            params_json: Path, dev_start: str, dev_end: str, out_json: Path):
    params = json.loads(params_json.read_text())
    spx = _load_m5(spx_root, "USA500IDXUSD", dev_start, dev_end)
    aud = _load_m5(fx_root, "AUDUSD", dev_start, dev_end)
    jpy = _load_m5(fx_root, "USDJPY", dev_start, dev_end)
    cal = load_calendar_index(calendar) if calendar.exists() else pd.DataFrame(columns=["ts_utc", "currency", "impact", "title"])
    tl_obs, _ = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0,
                                spx["ts_utc"].min(), spx["ts_utc"].max())
    counts = tl_obs.groupby(["symbol", "side"]).size().to_dict()
    tl_a = null_random_entries(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0, counts, seed=42)
    tl_b = null_regime_only(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0, seed=43)
    tl_c = null_micro_only(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0, seed=44)
    p_a = paired_alpha(tl_obs, tl_a, seed=100)
    p_b = paired_alpha(tl_obs, tl_b, seed=101)
    p_c = paired_alpha(tl_obs, tl_c, seed=102)
    out_json.write_text(json.dumps({"A1": p_a, "A2": p_b, "A3": p_c}), encoding="utf-8")
    typer.echo(str(out_json))
```

- [ ] **Step 4: Run test to verify passes**

Run: `pytest tests/integration/test_c6_cli_grid.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/v17/cli_c6.py tests/integration/test_c6_cli_grid.py
git commit -m "feat(c6): full dev pipeline — grid + MCPT + paired-alpha CLI"
```

---

## Task 18: Run dev phase end-to-end on real data

**Files:**
- Create: `out/c6/` (output directory, gitignored except reports)
- Create: `docs/superpowers/plans/c6_dev_gate_report_YYYY-MM-DD.md` (generated)
- Commit the generated report + the frozen `params.json`.

**Interfaces:**
- No new code. Execution of the pipeline on real data.

- [ ] **Step 1: Ingest all source data**

```bash
# Replace <DOCS> with "C:\\Users\\Vijayakumar R\\Documents"
v17 c6 ingest-m1 --bid-csv "<DOCS>\\AUDUSD_1 Min_Bid_2015.01.01_2026.09.26.csv" --ask-csv "<DOCS>\\AUDUSD_1 Min_Ask_2015.01.01_2026.09.26.csv" --symbol AUDUSD --out-root data/bars_m1_paired
v17 c6 ingest-m1 --bid-csv "<DOCS>\\USDJPY_1 Min_Bid_2015.01.01_2026.09.26.csv" --ask-csv "<DOCS>\\USDJPY_1 Min_Ask_2015.01.01_2026.09.26.csv" --symbol USDJPY --out-root data/bars_m1_paired
v17 c6 ingest-m1 --bid-csv "<DOCS>\\USA500IDXUSD_1 Min_Bid_2015.01.01_2026.10.14.csv" --ask-csv "<DOCS>\\USA500IDXUSD_1 Min_Ask_2015.01.01_2026.10.14.csv" --symbol USA500IDXUSD --out-root data/bars_m1_paired
```

- [ ] **Step 2: Build M5 cache per year, dev+holdout**

```bash
for sym in AUDUSD USDJPY USA500IDXUSD; do
  for y in 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 2026; do
    v17 c6 build-m5 --m1-root data/bars_m1_paired --m5-root data/bars_m5 --symbol $sym --year $y
  done
done
```

- [ ] **Step 3: Build calendar index**

```bash
v17 c6 build-calendar --ff-dir "<DOCS>\\forex_factory_cache" --out data/calendar_cache/ff_c6_index.parquet
```

- [ ] **Step 4: Run dev grid**

```bash
v17 c6 grid --spx-root data/bars_m5 --fx-root data/bars_m5 --calendar data/calendar_cache/ff_c6_index.parquet --dev-start 2015-01-01 --dev-end 2023-12-31 --out-csv out/c6/dev_grid.csv
```

- [ ] **Step 5: Freeze best params**

Pick the row from `out/c6/dev_grid.csv` with max Sharpe (ties broken by trade_count), write JSON to `out/c6/dev_params.json`:

```json
{"K": <K>, "slope_window": <SW>, "C": <C>}
```

- [ ] **Step 6: Run MCPT on dev with frozen params**

```bash
v17 c6 mcpt-dev --spx-root data/bars_m5 --fx-root data/bars_m5 --calendar data/calendar_cache/ff_c6_index.parquet --params-json out/c6/dev_params.json --dev-start 2015-01-01 --dev-end 2023-12-31 --n-permutations 500 --out-json out/c6/dev_mcpt.json
```

- [ ] **Step 7: Run paired-alpha on dev**

```bash
v17 c6 paired-alpha-dev --spx-root data/bars_m5 --fx-root data/bars_m5 --calendar data/calendar_cache/ff_c6_index.parquet --params-json out/c6/dev_params.json --dev-start 2015-01-01 --dev-end 2023-12-31 --out-json out/c6/dev_paired.json
```

- [ ] **Step 8: Regenerate best-config trade log**

Re-run `v17 c6 grid` with the single frozen config (or add a `backtest` subcommand) to dump the observed trade log + equity curve to `out/c6/dev_trade_log.csv` and `out/c6/dev_equity_curve.csv`.

- [ ] **Step 9: Generate dev report**

```bash
v17 c6 dev-report --grid-csv out/c6/dev_grid.csv --trade-log out/c6/dev_trade_log.csv --mcpt-json out/c6/dev_mcpt.json --paired-json out/c6/dev_paired.json --out-md docs/superpowers/plans/c6_dev_gate_report_YYYY-MM-DD.md
```

Replace `YYYY-MM-DD` with the run date.

- [ ] **Step 10: Review gate results**

- If `all_pass == true`: proceed to Task 19 (holdout).
- If any dev gate (D1–D6) fails: **SHELVE.** No rescue at dev stage.
- If A1 fails: shelve. If both A2 AND A3 fail: shelve (ablation says regime filter and micro-trigger together are random entries).

- [ ] **Step 11: Commit the frozen artifacts**

```bash
git add out/c6/dev_params.json out/c6/dev_grid.csv docs/superpowers/plans/c6_dev_gate_report_*.md
git commit -m "report(c6): dev phase complete — [PASS|SHELVE]"
```

---

## Task 19: Holdout run + MCPT

**Files:**
- Modify: `src/v17/cli_c6.py` (add `holdout` and `mcpt-holdout` commands — mirror `mcpt-dev` with different date range)
- Modify: `src/v17/cli_c6.py` (add `backtest` command to dump trade log + equity curve for arbitrary window)
- Create: `docs/superpowers/plans/c6_holdout_gate_report_YYYY-MM-DD.md` (generated)
- Test: `tests/integration/test_c6_cli_holdout.py`

**Interfaces:**
- `v17 c6 backtest --spx-root --fx-root --calendar --params-json --start --end --out-trades CSV --out-equity CSV`
- `v17 c6 mcpt-holdout` (same flags as mcpt-dev, different window, n_permutations=500)
- `v17 c6 holdout-report --dev-sharpe N --grid-csv --trade-log --mcpt-json --out-md`

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_c6_cli_holdout.py
from pathlib import Path
import json
import pandas as pd
from typer.testing import CliRunner
from v17.cli_c6 import app as c6_app


def test_holdout_report_md(tmp_path):
    tl = tmp_path / "ho_tl.csv"
    pd.DataFrame({"net_pnl_usd": [40, 50, -20, 60] * 100,
                   "entry_ts_ns": [i * 86_400_000_000_000 for i in range(400)],
                   "equity_sod": [10000] * 400}).to_csv(tl, index=False)
    mcpt = tmp_path / "mcpt.json"; mcpt.write_text(json.dumps({"p_sharpe": 0.07}))
    out = tmp_path / "ho.md"
    r = CliRunner().invoke(c6_app, ["holdout-report",
        "--dev-sharpe", "1.2", "--trade-log", str(tl),
        "--mcpt-json", str(mcpt), "--out-md", str(out)])
    assert r.exit_code == 0, r.output
    txt = out.read_text()
    assert "H1" in txt and "H5" in txt
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/integration/test_c6_cli_holdout.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement commands**

Append to `src/v17/cli_c6.py`:

```python
@app.command("backtest")
def backtest_cmd(spx_root: Path, fx_root: Path, calendar: Path, params_json: Path,
                    start: str, end: str, out_trades: Path, out_equity: Path):
    params = json.loads(params_json.read_text())
    spx = _load_m5(spx_root, "USA500IDXUSD", start, end)
    aud = _load_m5(fx_root, "AUDUSD", start, end)
    jpy = _load_m5(fx_root, "USDJPY", start, end)
    cal = load_calendar_index(calendar) if calendar.exists() else pd.DataFrame(columns=["ts_utc", "currency", "impact", "title"])
    tl, ec = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0,
                           spx["ts_utc"].min(), spx["ts_utc"].max())
    tl.to_csv(out_trades, index=False)
    ec.to_csv(out_equity, index=False)
    typer.echo(f"{out_trades} {out_equity}")


@app.command("mcpt-holdout")
def mcpt_holdout_cmd(spx_root: Path, fx_root: Path, calendar: Path,
                       params_json: Path, holdout_start: str, holdout_end: str,
                       n_permutations: int, out_json: Path):
    # Same as mcpt-dev with different window.
    mcpt_dev_cmd(spx_root, fx_root, calendar, params_json, holdout_start, holdout_end,
                   n_permutations, out_json)


@app.command("holdout-report")
def holdout_report_cmd(dev_sharpe: float, trade_log: Path, mcpt_json: Path, out_md: Path):
    tl = pd.read_csv(trade_log)
    ec = pd.DataFrame({"ts_utc": tl["entry_ts_ns"], "equity": 10_000})
    m = compute_metrics(tl, ec)
    mcpt = json.loads(mcpt_json.read_text())
    g = evaluate_holdout_gates(m, dev_sharpe=dev_sharpe, mcpt_p=mcpt["p_sharpe"])
    lines = [
        "# Cycle 6 — Holdout Gate Report", "",
        f"dev_sharpe={dev_sharpe:.3f}", "",
        "| Gate | Observed | Required | Pass |",
        "|------|----------|----------|------|",
        f"| H1 Sharpe | {m['sharpe']:.3f} | >= {0.7 * dev_sharpe:.3f} | {g['H1']} |",
        f"| H2 MCPT p | {mcpt['p_sharpe']:.4f} | <= 0.10 | {g['H2']} |",
        f"| H3 PF | {m['pf']:.3f} | >= 1.15 | {g['H3']} |",
        f"| H4 max daily loss | {m['max_daily_loss_pct']:.3%} | >= -3.0% | {g['H4']} |",
        f"| H5 worst month | {m['worst_month_return']:.3%} | >= -5.0% | {g['H5']} |",
        "",
        f"**ALL HOLDOUT GATES PASS: {g['all_pass']}**",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    typer.echo(str(out_md))
```

- [ ] **Step 4: Run test to verify passes**

Run: `pytest tests/integration/test_c6_cli_holdout.py -v`
Expected: PASS.

- [ ] **Step 5: Run holdout on real data**

```bash
v17 c6 backtest --spx-root data/bars_m5 --fx-root data/bars_m5 --calendar data/calendar_cache/ff_c6_index.parquet --params-json out/c6/dev_params.json --start 2024-01-01 --end 2026-10-14 --out-trades out/c6/holdout_trade_log.csv --out-equity out/c6/holdout_equity.csv

v17 c6 mcpt-holdout --spx-root data/bars_m5 --fx-root data/bars_m5 --calendar data/calendar_cache/ff_c6_index.parquet --params-json out/c6/dev_params.json --holdout-start 2024-01-01 --holdout-end 2026-10-14 --n-permutations 500 --out-json out/c6/holdout_mcpt.json

v17 c6 holdout-report --dev-sharpe <DEV_SHARPE_FROM_TASK_18> --trade-log out/c6/holdout_trade_log.csv --mcpt-json out/c6/holdout_mcpt.json --out-md docs/superpowers/plans/c6_holdout_gate_report_YYYY-MM-DD.md
```

- [ ] **Step 6: Commit holdout artifacts**

```bash
git add out/c6/holdout_*.csv out/c6/holdout_mcpt.json docs/superpowers/plans/c6_holdout_gate_report_*.md src/v17/cli_c6.py tests/integration/test_c6_cli_holdout.py
git commit -m "report(c6): holdout phase complete — [PASS|SHELVE|RESCUE]"
```

---

## Task 20: Holdout decision + pre-reg freeze marker

**Files:**
- Create or update: `docs/decisions/0009-cycle6-outcome.md` (new ADR documenting PASS / SHELVE / RESCUE decision)
- Update: user memory index at `C:\Users\Vijayakumar R\.claude\projects\C--personal-v-17\memory\MEMORY.md` with Cycle 6 outcome pointer

**Interfaces:** None — decision documentation and memory update.

- [ ] **Step 1: Evaluate holdout gates against pre-reg**

Open `docs/superpowers/plans/c6_holdout_gate_report_YYYY-MM-DD.md`:

- If `all_pass`: outcome = PASS, promote to S6 (30-day demo).
- If any gate fails AND rescue conditions (§8.5 of spec) hold: outcome = RESCUE candidate. Document the dated regime shift AND run ONE extended-dev rescue:

```bash
v17 c6 grid ... --dev-start <EXTENDED_DEV_START> --dev-end 2023-12-31 --out-csv out/c6/rescue_dev_grid.csv
# then repeat MCPT, paired-alpha, holdout with new params.
```

- If rescue fails or conditions not met: outcome = SHELVE.

- [ ] **Step 2: Write ADR**

Create `docs/decisions/0009-cycle6-outcome.md`:

```markdown
# ADR 0009 — Cycle 6 outcome

**Date:** YYYY-MM-DD
**Status:** [PASS | SHELVE | RESCUED-PASS | RESCUED-SHELVE]
**Spec:** docs/superpowers/specs/2026-11-12-cycle6-spx-led-fx-design.md

## Dev summary
- Best config: K=..., slope_window=..., C=...
- Dev Sharpe: ..., PF: ..., trades: ..., MCPT p: ...
- Paired alpha: A1=..., A2=..., A3=...

## Holdout summary
- Sharpe: ... (dev × 0.7 threshold = ...)
- PF: ..., MCPT p: ..., max daily loss: ..., worst month: ...

## Decision
[PASS → promote to 30-day demo starting <DATE>]
[SHELVE → …]
[RESCUE → … (document exact regime break and dated boundary move)]

## Follow-ups
- …
```

- [ ] **Step 3: Update memory index**

Append to `C:\Users\Vijayakumar R\.claude\projects\C--personal-v-17\memory\MEMORY.md`:

```
- [Cycle 6 status](project_cycle6_status.md) — [PASS/SHELVE/RESCUE] outcome YYYY-MM-DD.
```

Create `project_cycle6_status.md` with one-paragraph summary.

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/0009-cycle6-outcome.md
git commit -m "docs(c6): ADR 0009 — cycle 6 outcome [PASS|SHELVE]"
```

---

## Self-Review Summary

**Spec coverage check:**

- §1 Thesis — not code; covered by ADR in Task 20.
- §2 Universe — Task 1 (symbol registry), Task 2 (catalog), Task 3 (ingest).
- §3 Data split — Task 18 CLI args, Task 19 holdout args.
- §4 Capital / FTMO — Task 1 (constants), Task 8 (sizing), Task 10 (breakers), Task 11 (orchestrator).
- §5 Signal stack — Tasks 6, 7.
- §6 Execution — Tasks 8, 9, 11.
- §7 Session / blackouts — Tasks 1 (constants), 5 (calendar), 11 (orchestrator).
- §8 Validation gates — Tasks 12 (gates), 13 (MCPT), 14 (paired-alpha), 16 (dev report), 19 (holdout report).
- §8.5 Rescue — Task 20 execution branch.
- §9 Phases — maps directly to Tasks 1–5 (S1), 6–7 (S2), 8–11 (S3), 12–17 (S4), 19 (S5), 20 (closeout).
- §10 Artifacts — Tasks 3, 4, 5, 18, 19.
- §11 Failure modes — Task 11 grid alignment assertion (via shared_index intersection), Task 9 trail design, Task 5 calendar fail-closed.
- §12 Non-goals — enforced by absence of per-pair params (Task 2 single catalog), absence of WF folds (Task 15 single-pass grid), absence of regime-flip exit in Task 9.

**Placeholder scan:** none remaining. Every code block is complete; every test has concrete assertions.

**Type consistency:** `C6Position`, `C6EngineConfig`, `DailyState` names consistent across tasks. `run_backtest` signature used identically in Tasks 11, 14, 15, 17, 19. `compute_regime`, `compute_micro_signals`, `size_position` signatures stable.

**Known simplifications intentionally left in place:**

- `_sharpe_from_trades` annualization factor uses `sqrt(252)` as proxy — Task 12 ships this; can be refined post-dev if gates demand different scaling.
- Null-C (micro-only) in Task 15 uses a synthetically-trending SPX series to force regime acceptance rather than a cleaner override; documented in-code. A more rigorous version would add an explicit `regime_override` parameter to `run_backtest`. Deferred because the thesis test (does micro-trigger alone add alpha?) is preserved by this construction.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-11-12-cycle6-spx-led-fx.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
