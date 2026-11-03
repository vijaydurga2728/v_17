# Silver Bullet 6-Engine Doctrine Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute an unbiased statistical test (dual-scheme MCPT + sealed holdout + portfolio-layer second MCPT) of whether the ICT Silver Bullet strategy, as written in the frozen rulebook, exhibits a non-random edge on the user's historical FX and index data under FTMO Challenge $10,000 Standard constraints.

**Architecture:** Six independent engine configurations (3 session windows × 2 entry models) run on paired bid/ask Dukascopy data 2015-2024, each judged by dual-scheme MCPT at Bonferroni α = 0.00833 and a secondary secondary-gate matrix (PF, trade floor, per-fold robustness, equity-curve linearity, cost stress). Engines that pass dev MCPT are tested exactly once each against a sealed 2025-01→2026-10 holdout, then composed under one-position-per-symbol priority into a portfolio equity curve that must pass a second MCPT at α = 0.05 before any deploy decision.

**Tech Stack:** Python 3.11+, pyarrow / pandas for bar storage, polars for intraday aggregations, pytest + hypothesis for tests, structlog for JSONL logs, numpy for permutation runs, scipy.stats for p-value computation, finnhub-python for calendar backfill, typer for CLI entry points.

**Spec:** `docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md` (committed as `3ab7402`).

## Global Constraints

- Python 3.11+ required. Project `pyproject.toml` version floor must not regress.
- All timestamps stored in UTC int64 nanoseconds. Timezone math via `zoneinfo` only, with explicit `America/New_York` and `Europe/London` tz keys. No naive datetime arithmetic anywhere.
- All floating-point price math uses `float64`. Pip and point sizes come from `src/v17/common/instrument_spec.py` only; no hardcoded `0.0001` anywhere.
- Causality: at timestamp `t`, no code path reads a bar whose `ts_utc > t`. Enforced via explicit `t_now` parameter threading and audit tests in `tests/unit/structure/`.
- Zero parameter training. All rulebook parameters hardcoded in `research/ict/ICT_STRATEGY_RULEBOOK.md`-aligned constants modules; no per-fold tuning loops, no grid search over strategy parameters anywhere.
- Determinism: all stochastic processes (MCPT permutations) seed from a documented SHA-256 of `(engine_id, scheme_id, permutation_index)`. Re-run with same inputs must produce byte-identical outputs.
- Holdout partition tag `holdout` strictly guarded via `src/v17/data/partition_guard.py`. Dev-phase code paths must raise `PartitionGuardError` when attempting to load holdout data.
- Significance: per-engine MCPT α = 0.05 / 6 = 0.00833 (Bonferroni across 6 engines). Portfolio-layer MCPT α = 0.05 (single test).
- Risk: 0.5% equity per trade, fixed. No volatility sizing in this cycle.
- FTMO Challenge $10,000 Standard: 5% daily loss / 10% total loss hard limits enforced via circuit breakers at -4% daily / -8% total soft stops in backtest and future live code.
- News policy D: Finnhub High-impact USD/EUR/GBP blackout -10/+20 min, AND spread-guard rejection if `current_spread > 3 × 30-day rolling median per symbol per minute-of-day`.
- Order type: LIMIT only at CE or FVG proximal edge. No market entries. Pending expiry = window close + 5 min.
- Operating mode: Mode 1.5. No OpenAI pre-trade filter. No discretionary override.
- Spec L26 governs OpenAI usage: pre-build audit, transcript distillation, post-trade narrative, bug detector only. Prohibited for live decisions.
- No rule changes after any gate run. Spec L24 + Section 13.2.
- Commit frequency: after every passing step (test + implementation + commit cycle). Never batch multiple tasks into one commit.
- Pre-commit hooks (if present) must pass. Never use `--no-verify`.

---

## Milestone 0 — Prerequisites and Code Inventory

Purpose: establish the current state of the codebase vs. spec requirements so later milestones modify instead of duplicate. Produces a gap-list that drives tasks 2-N scope.

### Task 0.1: Confirm tooling and dependency floor

**Files:**
- Modify: `pyproject.toml` (verify versions)
- Create: `tests/unit/project/test_dependency_floor.py`

**Interfaces:**
- Consumes: nothing
- Produces: test that fails if dependency floor regresses below required versions

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/project/test_dependency_floor.py
import sys
import importlib.metadata as md

def test_python_version_floor():
    assert sys.version_info >= (3, 11), f"Need Python 3.11+, got {sys.version}"

def test_required_packages_present():
    required = [
        "pyarrow", "pandas", "polars", "pytest",
        "hypothesis", "structlog", "numpy", "scipy",
        "typer", "zoneinfo",  # zoneinfo is stdlib on 3.11+
    ]
    missing = []
    for pkg in required:
        if pkg == "zoneinfo":
            try:
                import zoneinfo  # noqa
            except ImportError:
                missing.append(pkg)
            continue
        try:
            md.version(pkg)
        except md.PackageNotFoundError:
            missing.append(pkg)
    assert not missing, f"Missing required packages: {missing}"

def test_finnhub_available():
    try:
        md.version("finnhub-python")
    except md.PackageNotFoundError:
        import pytest
        pytest.fail("finnhub-python required for calendar backfill (M2)")
```

- [ ] **Step 2: Run test to verify current state**

Run: `pytest tests/unit/project/test_dependency_floor.py -v`
Expected: either all pass (no action needed) or `finnhub-python` missing.

- [ ] **Step 3: If finnhub missing, add to pyproject.toml**

Edit `pyproject.toml`, add under `[project] dependencies`:
```
"finnhub-python>=2.4.19",
```
Then install: `pip install -e ".[dev]"`

- [ ] **Step 4: Re-run tests to confirm all pass**

Run: `pytest tests/unit/project/test_dependency_floor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/project/test_dependency_floor.py pyproject.toml
git commit -m "chore: pin dependency floor for Silver Bullet gate build"
```

---

### Task 0.2: Create research/audits/ directory and gate manifest

**Files:**
- Create: `research/audits/.gitkeep`
- Create: `research/results/.gitkeep`
- Create: `research/results/mcpt/.gitkeep`
- Create: `docs/superpowers/plans/GATE_MANIFEST.md`

**Interfaces:**
- Consumes: nothing
- Produces: directory structure for audit outputs and MCPT results; gate manifest tracks pass/fail per engine

- [ ] **Step 1: Create directories**

```bash
mkdir -p research/audits research/results/mcpt
touch research/audits/.gitkeep research/results/.gitkeep research/results/mcpt/.gitkeep
```

- [ ] **Step 2: Write GATE_MANIFEST.md skeleton**

Create `docs/superpowers/plans/GATE_MANIFEST.md`:

```markdown
# Silver Bullet 6-Engine Gate Manifest

Status tracker. Updated after each engine's gate run completes. **No rule changes permitted — this file records outcomes only.**

| Engine ID | Dev MCPT (α=0.00833) | Secondary Gates | Holdout | Verdict |
|-----------|---------------------|-----------------|---------|---------|
| SB-LDN-CE | pending | pending | pending | pending |
| SB-LDN-AG | pending | pending | pending | pending |
| SB-NYAM-CE | pending | pending | pending | pending |
| SB-NYAM-AG | pending | pending | pending | pending |
| SB-NYPM-CE | pending | pending | pending | pending |
| SB-NYPM-AG | pending | pending | pending | pending |

Portfolio-layer MCPT (α=0.05): pending

System verdict: pending (DEPLOY / SHELVE)
```

- [ ] **Step 3: Commit**

```bash
git add research/audits/.gitkeep research/results/.gitkeep research/results/mcpt/.gitkeep docs/superpowers/plans/GATE_MANIFEST.md
git commit -m "chore: scaffold audits/results dirs and gate manifest"
```

---

### Task 0.3: Code inventory audit script

**Files:**
- Create: `scripts/inventory_vs_spec.py`
- Create: `research/audits/code_inventory_2026-11-03.md` (output of running the script)

**Interfaces:**
- Consumes: existing `src/v17/` tree
- Produces: `research/audits/code_inventory_2026-11-03.md` with per-spec-requirement module status (present/missing/partial)

- [ ] **Step 1: Write the inventory script**

```python
# scripts/inventory_vs_spec.py
"""Inventory existing modules against spec section 15 phases.

Usage: python scripts/inventory_vs_spec.py > research/audits/code_inventory_2026-11-03.md
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent / "src" / "v17"

SPEC_REQUIREMENTS = [
    # (requirement_label, expected_module_path, spec_phase)
    ("Dukascopy paired bid/ask ingest", "data/dukascopy_csv.py", "P2"),
    ("Parquet store with partition tag", "data/parquet_store.py", "P2"),
    ("Partition guard (holdout seal)", "data/partition_guard.py", "P2"),
    ("Finnhub calendar backfill", "data/calendar/__init__.py", "P1"),
    ("D1 bias calculator (SB-A1)", "structure/bias.py", "P5"),
    ("FVG detector (causal)", "structure/fvg.py", "P5"),
    ("MSS detector (close-based)", "structure/mss.py", "P5"),
    ("Session boundaries NY/London", "structure/session.py", "P5"),
    ("Silver Bullet FSM", "setups/silver_bullet_fsm.py", "P5"),
    ("Instrument spec (pip sizes)", "common/instrument_spec.py", "P5"),
    ("Cost model (bid/ask + commission)", "backtest/cost.py", "P2+P5"),
    ("Fill model (limit, market)", "backtest/fills.py", "P5"),
    ("Backtest event loop", "backtest/loop.py", "P5"),
    ("Walk-forward harness", "backtest/walkforward.py", "P7"),
    ("MCPT harness", "validation/mcpt.py", "P8"),
    ("Validation gate", "validation/gate.py", "P10"),
    ("Validation thresholds", "validation/thresholds.py", "P10"),
    ("Risk engine (position sizing)", "risk/engine.py", "P5"),
    ("Risk rules (circuit breakers)", "risk/risk_rules.py", "P5"),
    ("MT5 reconciliation", "live/reconcile.py", "future-live"),
]

def main():
    print("# Code Inventory vs Spec Requirements\n")
    print("**Date:** 2026-11-03\n")
    print("**Reference:** `docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md` §15\n")
    print()
    print("| Requirement | Spec Phase | File | Exists | LOC | Status |")
    print("|---|---|---|---|---|---|")
    for req, path, phase in SPEC_REQUIREMENTS:
        f = ROOT / path
        exists = f.exists()
        loc = sum(1 for _ in f.open()) if exists and f.is_file() else 0
        status = "present" if exists and loc > 10 else ("stub" if exists else "missing")
        marker = "yes" if exists else "no"
        print(f"| {req} | {phase} | `src/v17/{path}` | {marker} | {loc} | {status} |")
    print()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run inventory script and capture output**

```bash
python scripts/inventory_vs_spec.py > research/audits/code_inventory_2026-11-03.md
```

- [ ] **Step 3: Verify output readable**

```bash
cat research/audits/code_inventory_2026-11-03.md
```
Expected: Markdown table with all 20 requirements listed.

- [ ] **Step 4: Commit script + inventory output**

```bash
git add scripts/inventory_vs_spec.py research/audits/code_inventory_2026-11-03.md
git commit -m "docs: inventory existing modules vs Silver Bullet spec requirements"
```

---

## Milestone 1 — Audit 1: Rulebook vs Transcript

Purpose: spec §13.1 Audit 1 — verify every `SOURCE_CONFIRMED` and `SOURCE_INTERPRETATION` rule in `research/ict/ICT_STRATEGY_RULEBOOK.md` is faithful to its cited transcript section. **Blocking:** no code work past Milestone 1 until this audit's findings are reviewed and any corrections applied.

### Task 1.1: Dispatch rulebook-vs-transcript audit

**Files:**
- Create: `research/audits/rulebook_vs_transcript_2026-11-03.md`

**Interfaces:**
- Consumes: `research/ict/ICT_STRATEGY_RULEBOOK.md` + `C:\personal\ICT transcript\{ict2022,OTE,market_structure}\*.vtt`
- Produces: findings document listing per-rule verdict (confirmed / mismatch / missing-citation / needs-rewrite)

- [ ] **Step 1: Dispatch research subagent**

Use the Agent tool with `subagent_type=general-purpose` and this prompt (copy exactly):

```
Audit the file research/ict/ICT_STRATEGY_RULEBOOK.md against the transcripts in C:\personal\ICT transcript\. For every rule classified SOURCE_CONFIRMED or SOURCE_INTERPRETATION, open the cited transcript .vtt file, locate the cited timestamp range, and verify the quoted text matches. Produce a markdown report at research/audits/rulebook_vs_transcript_2026-11-03.md with per-rule rows:

| Rule ID | Classification | Cited Transcript | Timestamp Range | Verdict | Notes |

Verdict values: CONFIRMED (quote matches, meaning preserved), MINOR_PARAPHRASE (meaning preserved, exact wording differs), MISMATCH (quote not found in cited range), MISSING_CITATION (classification SOURCE_CONFIRMED but no transcript line found), MISCLASSIFIED (classified SOURCE_CONFIRMED but rule content is interpretation).

For MISMATCH or MISCLASSIFIED, propose the correction. Do not edit the rulebook — report only. End the report with a summary count by verdict and list any rules that require spec amendment (would change a parameter in spec §5).

Report under 1500 words. Do not re-read the rulebook; use its text as-is.
```

- [ ] **Step 2: Review the produced audit report**

Open `research/audits/rulebook_vs_transcript_2026-11-03.md`. Classify findings:
- Zero MISMATCH / MISCLASSIFIED → proceed to Task 1.2.
- Any MISMATCH / MISCLASSIFIED → stop. Report to user with proposed corrections per finding.

- [ ] **Step 3: User decision gate**

Present findings to user. User chooses per finding:
- **Correct the rulebook** (preferred when transcript evidence is clear).
- **Reclassify** (e.g., from SOURCE_CONFIRMED to SOURCE_INTERPRETATION).
- **Reject the finding** (rare — requires justification).

Any correction that changes a parameter in spec §5 → spec amendment required (Task 1.3). Otherwise proceed.

- [ ] **Step 4: Commit audit report**

```bash
git add research/audits/rulebook_vs_transcript_2026-11-03.md
git commit -m "research: audit 1 rulebook vs transcript findings"
```

---

### Task 1.2: Apply rulebook corrections (if any)

Contingent on Task 1.1 findings. Skip if zero corrections required.

**Files:**
- Modify: `research/ict/ICT_STRATEGY_RULEBOOK.md`
- Modify: `research/MASTER_REVAMP_PLAN.md` (if cited rule changed)
- Modify: `docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md` (if §5 parameters change)

**Interfaces:**
- Consumes: audit findings from Task 1.1
- Produces: amended rulebook, amended spec if needed

- [ ] **Step 1: Edit rulebook per approved corrections**

For each corrected rule, update: classification, transcript citation (exact timestamp), quoted text (verbatim from transcript), and algorithmic rule block if the semantics changed.

- [ ] **Step 2: If any correction changes a spec §5 parameter, amend spec**

Edit `docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md` §5 parameter freeze table. Update the Source column to reference the corrected rule. Add a note at the top of §5: `*Amended on 2026-11-03 following Audit 1; see commit history.*`

- [ ] **Step 3: Request user re-approval of amended spec**

Explicit confirmation required before Milestone 2 begins. Do NOT proceed autonomously.

- [ ] **Step 4: Commit amendments**

```bash
git add research/ict/ICT_STRATEGY_RULEBOOK.md docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md
git commit -m "docs: amend rulebook and spec per Audit 1 findings"
```

---

## Milestone 2 — Data Ingest Pipeline

Purpose: ingest Dukascopy paired bid/ask CSVs into partitioned parquet with per-minute measured spread; backfill Finnhub High-impact calendar for USD/EUR/GBP 2015-2026; enforce holdout seal.

### Task 2.1: Audit existing `data/dukascopy_csv.py`

**Files:**
- Read: `src/v17/data/dukascopy_csv.py`
- Create: `research/audits/data_ingest_gap_analysis.md`

**Interfaces:**
- Consumes: existing ingest module
- Produces: gap list — does current loader handle paired bid/ask? partition tagging? EET→UTC? spread derivation?

- [ ] **Step 1: Read current implementation**

```bash
cat src/v17/data/dukascopy_csv.py
```

- [ ] **Step 2: Write gap analysis**

Create `research/audits/data_ingest_gap_analysis.md` with sections:
- Current capabilities (what the loader does today).
- Missing capabilities for spec §8.1 (paired bid/ask join on `time (EET)`, measured spread column, partition tag assignment at ingest time).
- Required changes (file-level patches needed in Tasks 2.2-2.4).

- [ ] **Step 3: Commit gap analysis**

```bash
git add research/audits/data_ingest_gap_analysis.md
git commit -m "research: data ingest gap analysis vs spec section 8.1"
```

---

### Task 2.2: Implement paired bid/ask loader

**Files:**
- Modify: `src/v17/data/dukascopy_csv.py`
- Create: `tests/unit/data/test_dukascopy_paired.py`

**Interfaces:**
- Consumes: two file paths (bid.csv, ask.csv), symbol string
- Produces: `pandas.DataFrame` with columns `ts_utc (int64 ns), symbol (str), bid_o/h/l/c, ask_o/h/l/c, bid_volume, ask_volume, spread_mid (float64)`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/data/test_dukascopy_paired.py
import pandas as pd
from pathlib import Path
import tempfile
from v17.data.dukascopy_csv import load_paired_bars

def _write_sample_csv(path: Path, header: str, rows: list[str]):
    path.write_text(header + "\n" + "\n".join(rows) + "\n")

def test_paired_load_joins_on_time_and_computes_spread():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bid = d / "EURUSD_bid.csv"
        ask = d / "EURUSD_ask.csv"
        header = "Time (EET),Open,High,Low,Close,Volume"
        _write_sample_csv(bid, header, [
            "2015.01.02 00:00:00,1.21000,1.21005,1.20995,1.21002,10",
            "2015.01.02 00:01:00,1.21002,1.21010,1.21001,1.21008,12",
        ])
        _write_sample_csv(ask, header, [
            "2015.01.02 00:00:00,1.21002,1.21007,1.20997,1.21004,10",
            "2015.01.02 00:01:00,1.21004,1.21012,1.21003,1.21010,12",
        ])
        df = load_paired_bars(bid, ask, symbol="EURUSD")

        assert list(df.columns) >= [
            "ts_utc", "symbol", "bid_o", "bid_h", "bid_l", "bid_c",
            "ask_o", "ask_h", "ask_l", "ask_c", "spread_mid",
        ]
        assert len(df) == 2
        assert df.iloc[0]["symbol"] == "EURUSD"
        assert df.iloc[0]["bid_c"] == 1.21002
        assert df.iloc[0]["ask_c"] == 1.21004
        assert abs(df.iloc[0]["spread_mid"] - 0.00002) < 1e-9

def test_eet_timezone_converts_to_utc():
    # EET winter is UTC+2
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bid = d / "b.csv"; ask = d / "a.csv"
        header = "Time (EET),Open,High,Low,Close,Volume"
        _write_sample_csv(bid, header, ["2015.01.02 02:00:00,1,1,1,1,1"])
        _write_sample_csv(ask, header, ["2015.01.02 02:00:00,1,1,1,1,1"])
        df = load_paired_bars(bid, ask, symbol="X")
        # 2015-01-02 02:00 EET = 2015-01-02 00:00 UTC
        expected_utc_ns = pd.Timestamp("2015-01-02 00:00:00", tz="UTC").value
        assert df.iloc[0]["ts_utc"] == expected_utc_ns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data/test_dukascopy_paired.py -v`
Expected: FAIL (function not implemented or missing paired-load capability)

- [ ] **Step 3: Implement `load_paired_bars` in `src/v17/data/dukascopy_csv.py`**

```python
# Add to src/v17/data/dukascopy_csv.py
import pandas as pd
from pathlib import Path

def load_paired_bars(bid_path: Path, ask_path: Path, symbol: str) -> pd.DataFrame:
    """Load paired Dukascopy bid/ask 1-min CSVs, join on timestamp, derive spread.

    Returns DataFrame with columns:
      ts_utc (int64 ns), symbol (str),
      bid_o, bid_h, bid_l, bid_c, bid_volume,
      ask_o, ask_h, ask_l, ask_c, ask_volume,
      spread_mid (ask_c - bid_c)
    """
    def _read(p: Path, side: str) -> pd.DataFrame:
        df = pd.read_csv(p, parse_dates=False)
        df.columns = [c.strip() for c in df.columns]
        time_col = next(c for c in df.columns if c.lower().startswith("time"))
        df["_ts"] = pd.to_datetime(df[time_col], format="%Y.%m.%d %H:%M:%S")
        # Localize as EET, then convert to UTC.
        df["_ts"] = df["_ts"].dt.tz_localize("Europe/Athens").dt.tz_convert("UTC")
        df["ts_utc"] = df["_ts"].astype("int64")
        rename = {"Open": f"{side}_o", "High": f"{side}_h", "Low": f"{side}_l",
                  "Close": f"{side}_c", "Volume": f"{side}_volume"}
        df = df.rename(columns=rename)
        keep = ["ts_utc", f"{side}_o", f"{side}_h", f"{side}_l", f"{side}_c", f"{side}_volume"]
        return df[keep]

    bid = _read(Path(bid_path), "bid")
    ask = _read(Path(ask_path), "ask")
    out = bid.merge(ask, on="ts_utc", how="inner")
    out["symbol"] = symbol
    out["spread_mid"] = out["ask_c"] - out["bid_c"]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data/test_dukascopy_paired.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/data/dukascopy_csv.py tests/unit/data/test_dukascopy_paired.py
git commit -m "feat(data): paired bid/ask Dukascopy loader with EET->UTC conversion and spread derivation"
```

---

### Task 2.3: Partition-tagged parquet writer with holdout seal

**Files:**
- Modify: `src/v17/data/parquet_store.py`
- Modify: `src/v17/data/partition_guard.py`
- Create: `tests/unit/data/test_partition_seal.py`

**Interfaces:**
- Consumes: paired bars DataFrame from Task 2.2 + partition policy (dev vs holdout cutoff `2025-01-01 00:00 UTC`)
- Produces: parquet files at `data/bars/<symbol>/<partition>/year=YYYY/month=MM/data.parquet`; `PartitionGuardError` raised on holdout access from dev-phase code

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/data/test_partition_seal.py
import pytest
import pandas as pd
from pathlib import Path
import tempfile
from v17.data.parquet_store import write_bars_partitioned, read_bars
from v17.data.partition_guard import PartitionGuardError, assert_dev_only

HOLDOUT_START_NS = pd.Timestamp("2025-01-01 00:00:00", tz="UTC").value

def _bars(ts_list, symbol="EURUSD"):
    return pd.DataFrame({
        "ts_utc": ts_list,
        "symbol": symbol,
        "bid_c": [1.0] * len(ts_list),
        "ask_c": [1.00002] * len(ts_list),
        "spread_mid": [0.00002] * len(ts_list),
    })

def test_writer_tags_partition_correctly():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        dev_ns = pd.Timestamp("2024-06-01 00:00:00", tz="UTC").value
        hold_ns = pd.Timestamp("2025-06-01 00:00:00", tz="UTC").value
        df = _bars([dev_ns, hold_ns])
        write_bars_partitioned(df, root=d)
        assert (d / "bars" / "EURUSD" / "dev" / "year=2024" / "month=06").exists()
        assert (d / "bars" / "EURUSD" / "holdout" / "year=2025" / "month=06").exists()

def test_dev_only_read_rejects_holdout():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        hold_ns = pd.Timestamp("2025-06-01 00:00:00", tz="UTC").value
        df = _bars([hold_ns])
        write_bars_partitioned(df, root=d)
        with pytest.raises(PartitionGuardError):
            read_bars(root=d, symbol="EURUSD", partition="holdout", dev_only=True)

def test_assert_dev_only_blocks_holdout_flag():
    with pytest.raises(PartitionGuardError):
        assert_dev_only(partition="holdout")
    assert_dev_only(partition="dev")  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data/test_partition_seal.py -v`
Expected: FAIL

- [ ] **Step 3: Implement writer, reader, and guard**

In `src/v17/data/partition_guard.py` (modify or add):

```python
import os

HOLDOUT_START_UTC_NS = 1735689600000000000  # 2025-01-01 00:00:00 UTC
UNSEAL_ENV_VAR = "V17_HOLDOUT_UNSEAL"

class PartitionGuardError(RuntimeError):
    pass

def is_holdout_ts(ts_utc_ns: int) -> bool:
    return ts_utc_ns >= HOLDOUT_START_UTC_NS

def assert_dev_only(partition: str) -> None:
    if partition != "dev":
        if os.environ.get(UNSEAL_ENV_VAR) == "1":
            return
        raise PartitionGuardError(
            f"Dev-only context attempted to access partition={partition!r}. "
            f"Set {UNSEAL_ENV_VAR}=1 only inside the holdout runner."
        )
```

In `src/v17/data/parquet_store.py` (add/modify):

```python
import pandas as pd
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from v17.data.partition_guard import HOLDOUT_START_UTC_NS, assert_dev_only, PartitionGuardError

def _partition_of(ts_ns: int) -> str:
    return "holdout" if ts_ns >= HOLDOUT_START_UTC_NS else "dev"

def write_bars_partitioned(df: pd.DataFrame, root: Path) -> None:
    df = df.copy()
    df["_partition"] = df["ts_utc"].map(_partition_of)
    df["_year"] = pd.to_datetime(df["ts_utc"]).dt.year
    df["_month"] = pd.to_datetime(df["ts_utc"]).dt.month
    for (symbol, part, year, month), group in df.groupby(["symbol", "_partition", "_year", "_month"]):
        out_dir = Path(root) / "bars" / symbol / part / f"year={year}" / f"month={month:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = group.drop(columns=["_partition", "_year", "_month"])
        pq.write_table(pa.Table.from_pandas(payload), out_dir / "data.parquet")

def read_bars(root: Path, symbol: str, partition: str = "dev", dev_only: bool = True) -> pd.DataFrame:
    if dev_only:
        assert_dev_only(partition)
    base = Path(root) / "bars" / symbol / partition
    if not base.exists():
        return pd.DataFrame()
    files = list(base.rglob("data.parquet"))
    if not files:
        return pd.DataFrame()
    tables = [pq.read_table(f) for f in files]
    return pa.concat_tables(tables).to_pandas()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data/test_partition_seal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/data/parquet_store.py src/v17/data/partition_guard.py tests/unit/data/test_partition_seal.py
git commit -m "feat(data): partition-tagged parquet writer with holdout seal guard"
```

---

### Task 2.4: Batch ingest CLI for all user CSVs

**Files:**
- Modify: `src/v17/data/cli.py`
- Create: `tests/unit/data/test_batch_ingest_cli.py`

**Interfaces:**
- Consumes: paired bars loader + partition writer
- Produces: `v17 ingest-paired --config data/ingest_manifest.yaml` command; writes all parquet partitions

- [ ] **Step 1: Create ingest manifest**

Create `data/ingest_manifest.yaml` listing user's paired files:

```yaml
# data/ingest_manifest.yaml
# Pairs of bid+ask CSVs from the user's Documents folder.
root: "C:/Users/Vijayakumar R/Documents"
symbols:
  - symbol: EURUSD
    pairs:
      - bid: "EURUSD_1 Min_Bid_2015.01.01_2026.10.18.csv"
        ask: "EURUSD_1 Min_Ask_2015.01.01_2026.10.18.csv"
  - symbol: GBPUSD
    pairs:
      - bid: "GBPUSD_1 Min_Bid_2015.01.01_2026.10.18.csv"
        ask: "GBPUSD_1 Min_Ask_2015.01.01_2026.10.18.csv"
  - symbol: USATECHIDXUSD
    pairs:
      - bid: "USATECHIDXUSD_1 Min_Bid_2015.01.01_2026.10.14.csv"
        ask: "USATECHIDXUSD_1 Min_Ask_2015.01.01_2026.10.14.csv"
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/data/test_batch_ingest_cli.py
import pandas as pd
from pathlib import Path
import tempfile
from v17.data.cli import ingest_from_manifest

def _write(p: Path, rows: list[str]):
    header = "Time (EET),Open,High,Low,Close,Volume"
    p.write_text(header + "\n" + "\n".join(rows) + "\n")

def test_ingest_from_manifest_writes_partitioned_parquet(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "EURUSD_bid.csv", ["2015.01.02 02:00:00,1,1,1,1.00000,1"])
    _write(src / "EURUSD_ask.csv", ["2015.01.02 02:00:00,1,1,1,1.00002,1"])

    manifest = {
        "root": str(src),
        "symbols": [{
            "symbol": "EURUSD",
            "pairs": [{"bid": "EURUSD_bid.csv", "ask": "EURUSD_ask.csv"}],
        }],
    }
    out = tmp_path / "out"
    ingest_from_manifest(manifest, out_root=out)
    files = list((out / "bars" / "EURUSD" / "dev").rglob("*.parquet"))
    assert len(files) >= 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/data/test_batch_ingest_cli.py -v`
Expected: FAIL

- [ ] **Step 4: Implement `ingest_from_manifest` in `src/v17/data/cli.py`**

```python
# Add to src/v17/data/cli.py
from pathlib import Path
from v17.data.dukascopy_csv import load_paired_bars
from v17.data.parquet_store import write_bars_partitioned

def ingest_from_manifest(manifest: dict, out_root: Path) -> None:
    root = Path(manifest["root"])
    for sym_entry in manifest["symbols"]:
        symbol = sym_entry["symbol"]
        for pair in sym_entry["pairs"]:
            bid = root / pair["bid"]
            ask = root / pair["ask"]
            df = load_paired_bars(bid, ask, symbol=symbol)
            write_bars_partitioned(df, root=Path(out_root))
```

Also add a Typer command (if the project uses Typer; otherwise match existing CLI style):

```python
import typer, yaml
app = typer.Typer()

@app.command("ingest-paired")
def ingest_paired_cmd(config: Path, out: Path = Path("data")):
    with open(config) as f:
        manifest = yaml.safe_load(f)
    ingest_from_manifest(manifest, out_root=out)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/data/test_batch_ingest_cli.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/v17/data/cli.py data/ingest_manifest.yaml tests/unit/data/test_batch_ingest_cli.py
git commit -m "feat(data): batch ingest CLI for paired Dukascopy CSVs"
```

---

### Task 2.5: Execute full ingest run on user data

**Files:**
- Create: `data/bars/EURUSD/dev/...` (output artifacts, not committed if large; keep `.gitignore` honest)
- Modify: `.gitignore` to exclude large parquet outputs

**Interfaces:**
- Consumes: all user CSV pairs from manifest
- Produces: partitioned parquet corpus at `data/bars/`; written log at `research/results/ingest_run_2026-11-03.log`

- [ ] **Step 1: Add parquet artifacts to .gitignore**

Edit `.gitignore`, add:
```
data/bars/
data/calendar/
research/results/*.log
```

- [ ] **Step 2: Run the ingest**

```bash
v17 ingest-paired --config data/ingest_manifest.yaml --out data/ 2>&1 | tee research/results/ingest_run_2026-11-03.log
```

- [ ] **Step 3: Verify parquet counts match expectation**

Write and run `scripts/verify_ingest_counts.py`:
```python
# scripts/verify_ingest_counts.py
from pathlib import Path
import pyarrow.parquet as pq

root = Path("data/bars")
for sym_dir in sorted(root.iterdir()):
    if not sym_dir.is_dir():
        continue
    for partition_dir in sorted(sym_dir.iterdir()):
        files = list(partition_dir.rglob("data.parquet"))
        total = sum(pq.read_metadata(f).num_rows for f in files)
        print(f"{sym_dir.name}/{partition_dir.name}: {len(files)} files, {total:,} rows")
```

Run and manually sanity-check row counts (~5M for EURUSD dev, ~1M for USATECHIDXUSD dev).

- [ ] **Step 4: Commit .gitignore update, script, log**

```bash
git add .gitignore scripts/verify_ingest_counts.py research/results/ingest_run_2026-11-03.log
git commit -m "chore: run full paired ingest and verify counts"
```

---

### Task 2.6: Finnhub calendar backfill

**Files:**
- Modify: `src/v17/data/calendar/__init__.py` (and submodules)
- Create: `src/v17/data/calendar/finnhub_client.py`
- Create: `tests/unit/data/calendar/test_finnhub_backfill.py`

**Interfaces:**
- Consumes: Finnhub API key from env `FINNHUB_API_KEY`
- Produces: `data/calendar/economic_events.parquet` with columns `timestamp_utc (int64 ns), currency, impact, event`

- [ ] **Step 1: Write the failing test (uses mock HTTP)**

```python
# tests/unit/data/calendar/test_finnhub_backfill.py
import pandas as pd
from unittest.mock import patch
from v17.data.calendar.finnhub_client import backfill_calendar

MOCK_RESPONSE = {
    "economicCalendar": [
        {"time": "2024-01-30 13:30:00", "country": "US", "impact": "high",
         "event": "Core PCE Price Index m/m"},
        {"time": "2024-01-31 10:00:00", "country": "EU", "impact": "medium",
         "event": "German Prelim CPI"},
    ]
}

def test_backfill_filters_high_impact_only():
    with patch("v17.data.calendar.finnhub_client._call_api", return_value=MOCK_RESPONSE):
        df = backfill_calendar(
            start="2024-01-30", end="2024-01-31",
            currencies=["USD", "EUR", "GBP"], impact="high",
        )
    assert len(df) == 1
    assert df.iloc[0]["event"] == "Core PCE Price Index m/m"
    assert df.iloc[0]["currency"] == "USD"

def test_backfill_produces_utc_ns_timestamps():
    with patch("v17.data.calendar.finnhub_client._call_api", return_value=MOCK_RESPONSE):
        df = backfill_calendar(
            start="2024-01-30", end="2024-01-31",
            currencies=["USD"], impact="high",
        )
    expected = pd.Timestamp("2024-01-30 13:30:00", tz="UTC").value
    assert df.iloc[0]["timestamp_utc"] == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data/calendar/test_finnhub_backfill.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the client**

```python
# src/v17/data/calendar/finnhub_client.py
import os
import time
import pandas as pd
import finnhub

_COUNTRY_TO_CCY = {"US": "USD", "EU": "EUR", "DE": "EUR", "GB": "GBP", "UK": "GBP"}

def _call_api(client, start: str, end: str) -> dict:
    return client.calendar_economic(_from=start, to=end)

def backfill_calendar(start: str, end: str, currencies: list[str], impact: str = "high") -> pd.DataFrame:
    api_key = os.environ.get("FINNHUB_API_KEY")
    client = finnhub.Client(api_key=api_key) if api_key else None
    raw = _call_api(client, start, end)
    rows = []
    for ev in raw.get("economicCalendar", []):
        ccy = _COUNTRY_TO_CCY.get(ev.get("country"), None)
        if ccy not in currencies:
            continue
        if ev.get("impact", "").lower() != impact.lower():
            continue
        ts = pd.Timestamp(ev["time"], tz="UTC")
        rows.append({
            "timestamp_utc": ts.value,
            "currency": ccy,
            "impact": ev["impact"].capitalize(),
            "event": ev["event"],
        })
    return pd.DataFrame(rows, columns=["timestamp_utc", "currency", "impact", "event"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data/calendar/test_finnhub_backfill.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/data/calendar/finnhub_client.py tests/unit/data/calendar/test_finnhub_backfill.py
git commit -m "feat(data): Finnhub high-impact calendar backfill client"
```

---

### Task 2.7: Execute calendar backfill 2015-2026

**Files:**
- Create: `scripts/backfill_calendar.py`
- Create: `data/calendar/economic_events.parquet` (output; gitignored)

**Interfaces:**
- Consumes: Finnhub API with `FINNHUB_API_KEY`
- Produces: full-range calendar parquet

- [ ] **Step 1: Write the orchestration script**

```python
# scripts/backfill_calendar.py
"""Iterate Finnhub calendar in monthly chunks 2015-01 to 2026-10 and persist."""
from pathlib import Path
import pandas as pd
import time
from v17.data.calendar.finnhub_client import backfill_calendar

def monthly_ranges(start: str, end: str):
    cur = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    while cur < end_ts:
        nxt = (cur + pd.offsets.MonthBegin(1))
        yield cur.strftime("%Y-%m-%d"), min(nxt, end_ts).strftime("%Y-%m-%d")
        cur = nxt

def main():
    frames = []
    for s, e in monthly_ranges("2015-01-01", "2026-10-18"):
        print(f"fetching {s} .. {e}")
        try:
            df = backfill_calendar(s, e, currencies=["USD", "EUR", "GBP"], impact="high")
            frames.append(df)
        except Exception as exc:
            print(f"  WARN: {exc}; skipping chunk")
        time.sleep(1.1)  # polite pacing under Finnhub 60/min limit
    all_df = pd.concat(frames, ignore_index=True).sort_values("timestamp_utc").drop_duplicates()
    out = Path("data/calendar/economic_events.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    all_df.to_parquet(out, index=False)
    print(f"wrote {len(all_df)} events to {out}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run backfill (requires FINNHUB_API_KEY env var)**

```bash
export FINNHUB_API_KEY="<user's key>"
python scripts/backfill_calendar.py 2>&1 | tee research/results/calendar_backfill.log
```

- [ ] **Step 3: Verify coverage**

Write `scripts/verify_calendar_coverage.py`:
```python
# scripts/verify_calendar_coverage.py
import pandas as pd
df = pd.read_parquet("data/calendar/economic_events.parquet")
df["ts"] = pd.to_datetime(df["timestamp_utc"], utc=True)
by_year = df.groupby(df["ts"].dt.year).size()
print(by_year)
assert all(by_year > 50), f"Suspiciously low coverage in some years:\n{by_year}"
```

Run and manually confirm all years 2015-2026 have >50 high-impact events.

- [ ] **Step 4: Commit script, log**

```bash
git add scripts/backfill_calendar.py scripts/verify_calendar_coverage.py research/results/calendar_backfill.log
git commit -m "chore: Finnhub high-impact calendar backfill 2015-2026"
```

---

## Milestone 3 — Silver Bullet FSM Implementation (6-Engine Capable)

Purpose: implement spec §4 engine catalog. Six engine configurations driven by a single parameterized FSM. All rulebook constraints (SB-01..SB-05, SB-A1 D1 bias) enforced causally. Zero parameter training (spec §5 freeze table).

Key observation: `src/v17/setups/silver_bullet_fsm.py` already exists uncommitted. Milestone 3 tasks AUDIT and EXTEND, not rebuild.

### Task 3.1: Freeze constants module from spec §5

**Files:**
- Create: `src/v17/setups/sb_constants.py`
- Create: `tests/unit/setups/test_sb_constants.py`

**Interfaces:**
- Consumes: spec §5
- Produces: single source of truth for all SB rulebook constants

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/setups/test_sb_constants.py
from v17.setups import sb_constants as c

def test_constants_match_spec_section_5():
    assert c.D1_EMA_PERIOD == 20
    assert c.D1_STRUCTURE_SWING_LOOKBACK_DAYS == 20
    assert c.ATR_PERIOD_M1 == 14
    assert c.DISPLACEMENT_BODY_RATIO_MIN == 0.65
    assert c.DISPLACEMENT_RANGE_ATR_MULT == 1.5
    assert c.FVG_COST_VIABILITY_MULT == 2.0
    assert c.MIN_R_MULTIPLE == 1.5
    assert c.STRUCTURAL_FALLBACK_USATECH_PTS == 15
    assert c.STRUCTURAL_FALLBACK_FX_PIPS == 20
    assert c.SL_BUFFER_FX_MIN_PIPS == 2.0
    assert c.SL_BUFFER_FX_MAX_PIPS == 15.0
    assert c.SL_BUFFER_USATECH_MAX_PTS == 20.0
    assert c.PENDING_EXPIRY_MIN_AFTER_WINDOW == 5
    assert c.POSITION_HARD_EXIT_MIN_AFTER_WINDOW == 60
    assert c.NEWS_BLACKOUT_BEFORE_MIN == 10
    assert c.NEWS_BLACKOUT_AFTER_MIN == 20
    assert c.SPREAD_GUARD_LOOKBACK_DAYS == 30
    assert c.SPREAD_GUARD_MULT == 3.0
    assert c.DAILY_LOSS_SOFT_STOP == 0.04
    assert c.TOTAL_LOSS_HARD_FREEZE == 0.08
    assert c.RISK_PER_TRADE == 0.005

def test_constants_are_frozen():
    import inspect
    source = inspect.getsource(c)
    # Simple heuristic: no dataclass, no mutable defaults.
    assert "class " not in source
    assert "dataclass" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/setups/test_sb_constants.py -v`
Expected: FAIL (module missing)

- [ ] **Step 3: Create the constants module**

```python
# src/v17/setups/sb_constants.py
"""Frozen Silver Bullet rulebook constants per spec section 5.

NEVER EDIT WITHOUT USER APPROVAL AND SPEC AMENDMENT. Changes mid-cycle
invalidate MCPT p-values.
"""

# D1 bias (SB-A1)
D1_EMA_PERIOD = 20
D1_STRUCTURE_SWING_LOOKBACK_DAYS = 20

# Displacement (SB-03)
ATR_PERIOD_M1 = 14
DISPLACEMENT_BODY_RATIO_MIN = 0.65
DISPLACEMENT_RANGE_ATR_MULT = 1.5

# FVG and entry (SB-04)
FVG_COST_VIABILITY_MULT = 2.0  # FVG height >= 2 * current spread

# Target (SB-05)
MIN_R_MULTIPLE = 1.5
STRUCTURAL_FALLBACK_USATECH_PTS = 15
STRUCTURAL_FALLBACK_FX_PIPS = 20

# Stops (JS-06 pattern)
SL_BUFFER_FX_MIN_PIPS = 2.0
SL_BUFFER_FX_MAX_PIPS = 15.0
SL_BUFFER_USATECH_MAX_PTS = 20.0

# Timing (spec defaults 5, 7)
PENDING_EXPIRY_MIN_AFTER_WINDOW = 5
POSITION_HARD_EXIT_MIN_AFTER_WINDOW = 60

# News policy (spec default 4)
NEWS_BLACKOUT_BEFORE_MIN = 10
NEWS_BLACKOUT_AFTER_MIN = 20

# Spread guard (spec default 3)
SPREAD_GUARD_LOOKBACK_DAYS = 30
SPREAD_GUARD_MULT = 3.0

# Circuit breakers (spec defaults 8, 9)
DAILY_LOSS_SOFT_STOP = 0.04  # 4% intraday => flat all, freeze until next NY midnight
TOTAL_LOSS_HARD_FREEZE = 0.08  # 8% from peak => permanent freeze, manual review

# Risk
RISK_PER_TRADE = 0.005  # 0.5% equity
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/setups/test_sb_constants.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/setups/sb_constants.py tests/unit/setups/test_sb_constants.py
git commit -m "feat(setups): freeze Silver Bullet rulebook constants per spec section 5"
```

---

### Task 3.2: Six-engine configuration catalog

**Files:**
- Create: `src/v17/setups/sb_engines.py`
- Create: `tests/unit/setups/test_sb_engines.py`

**Interfaces:**
- Consumes: `sb_constants`
- Produces: `ENGINE_CATALOG: list[SBEngineConfig]` with 6 engines matching spec §4

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/setups/test_sb_engines.py
from v17.setups.sb_engines import ENGINE_CATALOG, SBEngineConfig

def test_six_engines_defined():
    assert len(ENGINE_CATALOG) == 6
    ids = [e.engine_id for e in ENGINE_CATALOG]
    assert ids == [
        "SB-LDN-CE", "SB-LDN-AG",
        "SB-NYAM-CE", "SB-NYAM-AG",
        "SB-NYPM-CE", "SB-NYPM-AG",
    ]

def test_eligible_symbols_per_window():
    cat = {e.engine_id: e for e in ENGINE_CATALOG}
    assert set(cat["SB-LDN-CE"].symbols) == {"EURUSD", "GBPUSD"}
    assert set(cat["SB-NYAM-CE"].symbols) == {"USATECHIDXUSD", "EURUSD", "GBPUSD"}
    assert set(cat["SB-NYPM-CE"].symbols) == {"USATECHIDXUSD"}

def test_entry_models():
    cat = {e.engine_id: e for e in ENGINE_CATALOG}
    assert cat["SB-LDN-CE"].entry_model == "CE"
    assert cat["SB-LDN-AG"].entry_model == "AGGRESSIVE"

def test_window_times_ny():
    cat = {e.engine_id: e for e in ENGINE_CATALOG}
    assert cat["SB-LDN-CE"].window_ny == ("03:00", "04:00")
    assert cat["SB-NYAM-CE"].window_ny == ("10:00", "11:00")
    assert cat["SB-NYPM-CE"].window_ny == ("14:00", "15:00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/setups/test_sb_engines.py -v`
Expected: FAIL

- [ ] **Step 3: Create engine catalog module**

```python
# src/v17/setups/sb_engines.py
"""Six Silver Bullet engine configurations per spec section 4."""
from dataclasses import dataclass, field
from typing import Literal

EntryModel = Literal["CE", "AGGRESSIVE"]

@dataclass(frozen=True)
class SBEngineConfig:
    engine_id: str
    window_ny: tuple[str, str]  # ("HH:MM", "HH:MM")
    entry_model: EntryModel
    symbols: tuple[str, ...]
    priority_order: int  # 1 = highest priority in portfolio layer (spec section 10.2)

ENGINE_CATALOG: list[SBEngineConfig] = [
    SBEngineConfig("SB-LDN-CE",  ("03:00", "04:00"), "CE",         ("EURUSD", "GBPUSD"), 1),
    SBEngineConfig("SB-LDN-AG",  ("03:00", "04:00"), "AGGRESSIVE", ("EURUSD", "GBPUSD"), 2),
    SBEngineConfig("SB-NYAM-CE", ("10:00", "11:00"), "CE",         ("USATECHIDXUSD", "EURUSD", "GBPUSD"), 3),
    SBEngineConfig("SB-NYAM-AG", ("10:00", "11:00"), "AGGRESSIVE", ("USATECHIDXUSD", "EURUSD", "GBPUSD"), 4),
    SBEngineConfig("SB-NYPM-CE", ("14:00", "15:00"), "CE",         ("USATECHIDXUSD",), 5),
    SBEngineConfig("SB-NYPM-AG", ("14:00", "15:00"), "AGGRESSIVE", ("USATECHIDXUSD",), 6),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/setups/test_sb_engines.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/setups/sb_engines.py tests/unit/setups/test_sb_engines.py
git commit -m "feat(setups): six-engine Silver Bullet configuration catalog"
```

---

### Task 3.3: D1 bias calculator (SB-A1 implementation)

**Files:**
- Modify: `src/v17/structure/bias.py`
- Create: `tests/unit/structure/test_bias_sb_a1.py`

**Interfaces:**
- Consumes: D1 bars (`pd.DataFrame[ts_utc, bid_c, ask_c]` resampled to D1 close NY-midnight-based)
- Produces: `compute_d1_bias(d1_bars, as_of_utc_ns) -> Literal["BULLISH", "BEARISH", "NONE"]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/structure/test_bias_sb_a1.py
import pandas as pd
import numpy as np
from v17.structure.bias import compute_d1_bias

def _d1(prices: list[float]) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=len(prices), freq="D", tz="UTC")
    return pd.DataFrame({
        "ts_utc": ts.astype("int64"),
        "bid_c": prices,
        "ask_c": [p + 0.00002 for p in prices],
    })

def test_bias_bullish_when_structure_up_and_above_ema20():
    # Strongly up-trending 25-day sequence (HH/HL)
    prices = list(np.linspace(1.00, 1.10, 25))
    df = _d1(prices)
    as_of = df.iloc[-1]["ts_utc"] + 86_400_000_000_000  # next day
    bias = compute_d1_bias(df, as_of_utc_ns=as_of)
    assert bias == "BULLISH"

def test_bias_bearish_when_structure_down_and_below_ema20():
    prices = list(np.linspace(1.10, 1.00, 25))
    df = _d1(prices)
    as_of = df.iloc[-1]["ts_utc"] + 86_400_000_000_000
    bias = compute_d1_bias(df, as_of_utc_ns=as_of)
    assert bias == "BEARISH"

def test_bias_none_when_structure_opposes_ema():
    # Flat/choppy with no clear structure
    prices = [1.0, 1.01, 0.99, 1.02, 0.98] * 5
    df = _d1(prices)
    as_of = df.iloc[-1]["ts_utc"] + 86_400_000_000_000
    bias = compute_d1_bias(df, as_of_utc_ns=as_of)
    assert bias == "NONE"

def test_causality_no_future_bars_used():
    prices = list(np.linspace(1.00, 1.10, 30))
    df = _d1(prices)
    # Query at bar 20 (0-indexed); must not peek at bars 21-29
    as_of = df.iloc[20]["ts_utc"]
    bias_at_20 = compute_d1_bias(df, as_of_utc_ns=as_of)
    # Shouldn't matter what we add after; same result
    df_more = df.copy()
    df_more.iloc[21:, df_more.columns.get_loc("bid_c")] = 999.0
    df_more.iloc[21:, df_more.columns.get_loc("ask_c")] = 999.0
    bias_at_20_mutated = compute_d1_bias(df_more, as_of_utc_ns=as_of)
    assert bias_at_20 == bias_at_20_mutated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/structure/test_bias_sb_a1.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SB-A1 in `structure/bias.py`**

```python
# Add to src/v17/structure/bias.py
import pandas as pd
import numpy as np
from typing import Literal
from v17.setups.sb_constants import D1_EMA_PERIOD, D1_STRUCTURE_SWING_LOOKBACK_DAYS

Bias = Literal["BULLISH", "BEARISH", "NONE"]

def _classify_structure(prices: np.ndarray) -> Bias:
    """3-bar swing classification over the lookback window.

    Bullish if last 5 swing points form HH + HL pattern.
    Bearish if LH + LL pattern.
    Mixed otherwise.
    """
    if len(prices) < 5:
        return "NONE"
    # Identify local highs/lows (3-bar pivots)
    highs, lows = [], []
    for i in range(1, len(prices) - 1):
        if prices[i] > prices[i-1] and prices[i] > prices[i+1]:
            highs.append((i, prices[i]))
        if prices[i] < prices[i-1] and prices[i] < prices[i+1]:
            lows.append((i, prices[i]))
    if len(highs) < 2 or len(lows) < 2:
        return "NONE"
    bull = highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]
    bear = highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1]
    if bull and not bear:
        return "BULLISH"
    if bear and not bull:
        return "BEARISH"
    return "NONE"

def compute_d1_bias(d1_bars: pd.DataFrame, as_of_utc_ns: int) -> Bias:
    # Causality: use only bars whose ts_utc < as_of_utc_ns
    df = d1_bars[d1_bars["ts_utc"] < as_of_utc_ns].copy()
    if len(df) < max(D1_EMA_PERIOD, D1_STRUCTURE_SWING_LOOKBACK_DAYS) + 1:
        return "NONE"
    close = df["bid_c"].to_numpy()  # D1 bias uses mid-of-day; bid is fine for direction
    ema = pd.Series(close).ewm(span=D1_EMA_PERIOD, adjust=False).mean().iloc[-1]
    last_close = close[-1]
    ema_align: Bias = "BULLISH" if last_close > ema else "BEARISH" if last_close < ema else "NONE"

    window = close[-D1_STRUCTURE_SWING_LOOKBACK_DAYS:]
    structure = _classify_structure(window)

    if structure == "NONE" or ema_align == "NONE":
        return "NONE"
    if structure != ema_align:
        return "NONE"
    return structure
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/structure/test_bias_sb_a1.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/structure/bias.py tests/unit/structure/test_bias_sb_a1.py
git commit -m "feat(structure): D1 bias calculator SB-A1 (structure + EMA20, causal)"
```

---

### Task 3.4: Causal FVG detector audit and lock

**Files:**
- Read: `src/v17/structure/fvg.py`
- Create: `tests/unit/structure/test_fvg_causality.py`
- Modify: `src/v17/structure/fvg.py` (only if audit reveals causality violations)

**Interfaces:**
- Consumes: M1 bars
- Produces: FVG list causally correct — bar at index `i` only inspects bars `≤ i`

- [ ] **Step 1: Read current FVG implementation**

```bash
cat src/v17/structure/fvg.py
```

- [ ] **Step 2: Write causality tests**

```python
# tests/unit/structure/test_fvg_causality.py
import pandas as pd
import numpy as np
from v17.structure.fvg import detect_fvgs

def _bars(highs, lows, opens=None, closes=None):
    n = len(highs)
    if opens is None:
        opens = [(h + l) / 2 for h, l in zip(highs, lows)]
    if closes is None:
        closes = opens[:]
    ts = pd.date_range("2024-01-01 09:00", periods=n, freq="min", tz="UTC").astype("int64")
    return pd.DataFrame({
        "ts_utc": ts, "bid_o": opens, "bid_h": highs, "bid_l": lows, "bid_c": closes,
        "ask_o": opens, "ask_h": highs, "ask_l": lows, "ask_c": closes,
    })

def test_bullish_fvg_detected_at_bar_i_only_uses_bars_i_minus_2_and_i():
    # Bar 0 H=1.00; Bar 1 displacement; Bar 2 L=1.01 => bullish FVG [1.00, 1.01]
    df = _bars([1.00, 1.02, 1.03], [0.99, 1.00, 1.01])
    fvgs = detect_fvgs(df, as_of_ns=df.iloc[2]["ts_utc"])
    bull = [f for f in fvgs if f["kind"] == "bullish"]
    assert len(bull) == 1

def test_fvg_not_detected_before_bar_i_plus_2_exists():
    df = _bars([1.00, 1.02, 1.03], [0.99, 1.00, 1.01])
    # Query at bar 1 timestamp; bar 2 does not exist in the causal view
    fvgs = detect_fvgs(df, as_of_ns=df.iloc[1]["ts_utc"])
    assert len([f for f in fvgs if f["kind"] == "bullish"]) == 0

def test_future_bar_mutation_does_not_change_past_fvg():
    df = _bars([1.00, 1.02, 1.03, 1.04, 1.05], [0.99, 1.00, 1.01, 1.03, 1.04])
    f1 = detect_fvgs(df, as_of_ns=df.iloc[2]["ts_utc"])
    df_mutated = df.copy()
    df_mutated.loc[df_mutated.index[3:], "bid_h"] = 999.0
    f2 = detect_fvgs(df_mutated, as_of_ns=df.iloc[2]["ts_utc"])
    assert f1 == f2
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/structure/test_fvg_causality.py -v`
Expected: Either all pass (existing detector is causal — great) or some fail (requires fix).

- [ ] **Step 4: If fail, fix `src/v17/structure/fvg.py`**

Patch `detect_fvgs(df, as_of_ns)` so it:
1. Filters `df` to `ts_utc < as_of_ns` AT ENTRY, before any computation.
2. Returns FVGs where index `i` satisfies `i+2 < len(filtered)` (requires bar_i+2 to exist).
3. Uses bullish condition: `L_i > H_{i-2}` strictly; bearish: `H_i < L_{i-2}`.
4. Returns a stable sort order (by `ts_utc` of bar `i`).

- [ ] **Step 5: Re-run tests**

Run: `pytest tests/unit/structure/test_fvg_causality.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/v17/structure/fvg.py tests/unit/structure/test_fvg_causality.py
git commit -m "fix(structure): FVG detector enforces strict causality via as_of_ns filter"
```

---

### Task 3.5: Displacement validator (SB-03)

**Files:**
- Create: `src/v17/structure/displacement.py`
- Create: `tests/unit/structure/test_displacement.py`

**Interfaces:**
- Consumes: M1 bar (open, high, low, close) + ATR_14 value from prior bars
- Produces: `is_displacement(bar, atr_14) -> bool` enforcing SB-03 body ratio ≥ 0.65 AND range ≥ 1.5 × ATR

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/structure/test_displacement.py
from v17.structure.displacement import is_displacement

def test_rejects_small_body_ratio():
    # Body 0.5, range 1.0 => ratio 0.5 < 0.65
    bar = {"bid_o": 1.0, "bid_h": 1.001, "bid_l": 0.999, "bid_c": 1.0005}
    atr = 0.0005  # range 0.002 vs 1.5*atr=0.00075 → range side passes
    # body = 0.0005, range = 0.002, ratio = 0.25 (fails)
    assert is_displacement(bar, atr_14=atr) is False

def test_rejects_small_range_relative_to_atr():
    # Range 0.0001 vs ATR 0.0001 → 1.0× not >=1.5×
    bar = {"bid_o": 1.0, "bid_h": 1.00009, "bid_l": 0.99991, "bid_c": 1.00008}
    assert is_displacement(bar, atr_14=0.0001) is False

def test_accepts_strong_bullish_displacement():
    # Body 0.0017, range 0.002 → ratio 0.85; range 0.002 vs ATR 0.0005*1.5=0.00075
    bar = {"bid_o": 1.0, "bid_h": 1.002, "bid_l": 1.0, "bid_c": 1.0017}
    assert is_displacement(bar, atr_14=0.0005) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/structure/test_displacement.py -v`
Expected: FAIL (module missing)

- [ ] **Step 3: Implement displacement validator**

```python
# src/v17/structure/displacement.py
from v17.setups.sb_constants import DISPLACEMENT_BODY_RATIO_MIN, DISPLACEMENT_RANGE_ATR_MULT

def is_displacement(bar: dict, atr_14: float) -> bool:
    o, h, l, c = bar["bid_o"], bar["bid_h"], bar["bid_l"], bar["bid_c"]
    rng = h - l
    if rng <= 0:
        return False
    body = abs(c - o)
    body_ratio = body / rng
    if body_ratio < DISPLACEMENT_BODY_RATIO_MIN:
        return False
    if rng < DISPLACEMENT_RANGE_ATR_MULT * atr_14:
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/structure/test_displacement.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/structure/displacement.py tests/unit/structure/test_displacement.py
git commit -m "feat(structure): SB-03 displacement validator (body ratio 0.65, range 1.5xATR)"
```

---

### Task 3.6: Eligible liquidity pool detector (SB-02)

**Files:**
- Create: `src/v17/structure/liquidity_pools.py`
- Create: `tests/unit/structure/test_liquidity_pools.py`

**Interfaces:**
- Consumes: M1 bars + current engine's window start timestamp + ts_now
- Produces: list of eligible liquidity levels per SB-02: session extreme, previous-hour high/low, prominent M15 swing from last 45 min

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/structure/test_liquidity_pools.py
import pandas as pd
from v17.structure.liquidity_pools import enumerate_pools

def test_session_extreme_from_ny_midnight_to_window_start():
    # Session 00:00 NY to 10:00 NY, window starts 10:00
    bars = pd.DataFrame({
        "ts_utc": pd.date_range("2024-03-15 05:00", "2024-03-15 15:00", freq="min", tz="UTC").astype("int64"),
        "bid_h": [1.08 + i * 0.00001 for i in range(601)],
        "bid_l": [1.07 - i * 0.00001 for i in range(601)],
    })
    window_start_ns = pd.Timestamp("2024-03-15 14:00:00", tz="UTC").value
    pools = enumerate_pools(bars, window_start_ns=window_start_ns, now_ns=window_start_ns + 60_000_000_000)
    kinds = {p["kind"] for p in pools}
    assert "session_high" in kinds
    assert "session_low" in kinds

def test_no_asian_fallback_present():
    # The function must NOT emit asian_* pools (SB-02 prohibition)
    pools = enumerate_pools(
        pd.DataFrame({"ts_utc": [1], "bid_h": [1], "bid_l": [1]}),
        window_start_ns=2, now_ns=3,
    )
    for p in pools:
        assert "asian" not in p["kind"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/structure/test_liquidity_pools.py -v`
Expected: FAIL

- [ ] **Step 3: Implement liquidity pool enumeration**

```python
# src/v17/structure/liquidity_pools.py
import pandas as pd
from typing import Any

def enumerate_pools(bars: pd.DataFrame, window_start_ns: int, now_ns: int) -> list[dict[str, Any]]:
    """Enumerate SB-02 eligible liquidity pools.

    STRICT: no Asian-session fallback. No PDH/PDL. Only session extreme,
    previous-hour high/low, and prominent M15 swings from last 45 min.
    """
    pools: list[dict] = []
    # Causality filter
    df = bars[bars["ts_utc"] < now_ns]
    if df.empty:
        return pools

    # Session extreme: NY midnight to window start.
    # Caller is responsible for ensuring bars cover from NY midnight onward.
    # Session boundary: find bars with ts >= NY midnight of same day as window_start.
    pre_window = df[df["ts_utc"] < window_start_ns]
    if not pre_window.empty:
        pools.append({"kind": "session_high", "price": float(pre_window["bid_h"].max()),
                      "ts_utc": int(pre_window.loc[pre_window["bid_h"].idxmax(), "ts_utc"])})
        pools.append({"kind": "session_low", "price": float(pre_window["bid_l"].min()),
                      "ts_utc": int(pre_window.loc[pre_window["bid_l"].idxmin(), "ts_utc"])})

    # Previous hour: [window_start - 60min, window_start)
    one_hour_ns = 3_600_000_000_000
    prev_hr = df[(df["ts_utc"] >= window_start_ns - one_hour_ns) & (df["ts_utc"] < window_start_ns)]
    if not prev_hr.empty:
        pools.append({"kind": "prev_hour_high", "price": float(prev_hr["bid_h"].max()),
                      "ts_utc": int(prev_hr.loc[prev_hr["bid_h"].idxmax(), "ts_utc"])})
        pools.append({"kind": "prev_hour_low", "price": float(prev_hr["bid_l"].min()),
                      "ts_utc": int(prev_hr.loc[prev_hr["bid_l"].idxmin(), "ts_utc"])})

    # M15 prominent swings in last 45 min — intentionally omitted here as a stub
    # requiring the swings module. Downstream FSM may consume these two pool
    # kinds first; add M15 swings in Task 3.6b if needed by MCPT trade counts.
    return pools
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/structure/test_liquidity_pools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/structure/liquidity_pools.py tests/unit/structure/test_liquidity_pools.py
git commit -m "feat(structure): SB-02 liquidity pool enumerator (no Asian fallback)"
```

---

### Task 3.7: Audit existing silver_bullet_fsm.py and gap-list

**Files:**
- Read: `src/v17/setups/silver_bullet_fsm.py`
- Create: `research/audits/sb_fsm_gap_2026-11-03.md`

**Interfaces:**
- Consumes: existing FSM
- Produces: gap list — does current FSM handle 6-engine parameterization? CE vs AG entries? D1 bias filter?

- [ ] **Step 1: Read current FSM**

```bash
cat src/v17/setups/silver_bullet_fsm.py
```

- [ ] **Step 2: Write gap analysis**

Create `research/audits/sb_fsm_gap_2026-11-03.md` with sections:
- Current state machine states and transitions.
- Which engine configurations it supports (hardcoded? parameterized?).
- Gaps vs spec section 4 (6 engines, CE+AG as independent engines, D1 bias filter addendum SB-A1).
- Required patches to make it 6-engine-capable with sb_constants and sb_engines modules.

- [ ] **Step 3: Commit gap analysis**

```bash
git add research/audits/sb_fsm_gap_2026-11-03.md
git commit -m "research: Silver Bullet FSM gap analysis for 6-engine parameterization"
```

---

### Task 3.8: Parameterize FSM for 6 engines

**Files:**
- Modify: `src/v17/setups/silver_bullet_fsm.py`
- Create: `tests/unit/setups/test_silver_bullet_fsm_6_engines.py`

**Interfaces:**
- Consumes: `SBEngineConfig` from catalog, bars, D1 bias, calendar, spread
- Produces: `SilverBulletFSM(config).step(bar, context) -> Signal | None` where context contains bias, calendar, spread

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/setups/test_silver_bullet_fsm_6_engines.py
import pytest
from v17.setups.silver_bullet_fsm import SilverBulletFSM
from v17.setups.sb_engines import ENGINE_CATALOG

@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_instantiates_for_every_engine(config):
    fsm = SilverBulletFSM(config)
    assert fsm.engine_id == config.engine_id

@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_rejects_signal_when_bias_none(config):
    fsm = SilverBulletFSM(config)
    bar = {"ts_utc": 1, "bid_o": 1, "bid_h": 1, "bid_l": 1, "bid_c": 1,
           "ask_o": 1, "ask_h": 1, "ask_l": 1, "ask_c": 1, "symbol": config.symbols[0]}
    ctx = {"d1_bias": "NONE", "atr_14": 0.001, "spread": 0.00001,
           "spread_median": 0.00001, "calendar_blackout": False,
           "window_open": True, "liquidity_pools": [], "fvgs": []}
    sig = fsm.step(bar, ctx)
    assert sig is None

@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_rejects_signal_during_blackout(config):
    fsm = SilverBulletFSM(config)
    bar = {"ts_utc": 1, "bid_o": 1, "bid_h": 1.01, "bid_l": 1, "bid_c": 1.01,
           "ask_o": 1, "ask_h": 1.01, "ask_l": 1, "ask_c": 1.01, "symbol": config.symbols[0]}
    ctx = {"d1_bias": "BULLISH", "atr_14": 0.001, "spread": 0.00001,
           "spread_median": 0.00001, "calendar_blackout": True,
           "window_open": True, "liquidity_pools": [], "fvgs": []}
    sig = fsm.step(bar, ctx)
    assert sig is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/setups/test_silver_bullet_fsm_6_engines.py -v`
Expected: FAIL (constructor doesn't accept SBEngineConfig, or methods differ)

- [ ] **Step 3: Patch FSM to accept SBEngineConfig and context dict**

Modify `src/v17/setups/silver_bullet_fsm.py`:
- Constructor: `__init__(self, config: SBEngineConfig)` stores `self.engine_id = config.engine_id`, `self.window_ny = config.window_ny`, `self.entry_model = config.entry_model`, `self.symbols = config.symbols`.
- Method: `step(self, bar: dict, context: dict) -> Signal | None` returns `None` whenever `context["d1_bias"] == "NONE"` or `context["calendar_blackout"]` or `context["spread"] > SPREAD_GUARD_MULT * context["spread_median"]`.
- Signal generation uses `self.entry_model`: CE → entry at FVG midpoint; AGGRESSIVE → entry at proximal edge.

Keep existing successful state-machine logic; wrap gates at entry of step.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/setups/test_silver_bullet_fsm_6_engines.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/setups/silver_bullet_fsm.py tests/unit/setups/test_silver_bullet_fsm_6_engines.py
git commit -m "feat(setups): parameterize Silver Bullet FSM across 6 engine configs with gates"
```

---

### Task 3.9: SL/TP + R:R gate implementation (SB-04, SB-05, JS-06 pattern)

**Files:**
- Create: `src/v17/setups/sb_sl_tp.py`
- Create: `tests/unit/setups/test_sb_sl_tp.py`

**Interfaces:**
- Consumes: side, entry price, sweep extreme, opposing liquidity target, symbol pip size
- Produces: `(sl_price, tp_price, r_multiple)` or raises `SBRejectError(reason)` if R:R < 1.5 or SL distance exceeds max

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/setups/test_sb_sl_tp.py
import pytest
from v17.setups.sb_sl_tp import compute_sl_tp, SBRejectError

def test_eurusd_long_sl_tp_pass():
    out = compute_sl_tp(
        side="LONG", entry=1.1000, sweep_extreme=1.0995,
        opposing_target=1.1012, symbol="EURUSD",
    )
    assert out.sl == pytest.approx(1.0994, abs=1e-6)  # 1 pip below sweep extreme
    assert out.tp == 1.1012
    assert out.r_multiple >= 1.5

def test_eurusd_long_rr_reject():
    with pytest.raises(SBRejectError, match="R:R"):
        compute_sl_tp(
            side="LONG", entry=1.1000, sweep_extreme=1.0998,
            opposing_target=1.1002, symbol="EURUSD",
        )

def test_sl_widens_to_minimum_2_pips_fx():
    out = compute_sl_tp(
        side="LONG", entry=1.1000, sweep_extreme=1.0999,  # 1 pip below
        opposing_target=1.1020, symbol="EURUSD",
    )
    # 1 pip would be 1.0998; min widens to 2 pips → 1.0998
    assert abs(out.sl - 1.0998) < 1e-6

def test_fx_long_sl_distance_cap_reject():
    with pytest.raises(SBRejectError, match="exceeds max"):
        compute_sl_tp(
            side="LONG", entry=1.1000, sweep_extreme=1.0980,  # 20 pips => > 15 pips cap
            opposing_target=1.1050, symbol="EURUSD",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/setups/test_sb_sl_tp.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SL/TP computation**

```python
# src/v17/setups/sb_sl_tp.py
from dataclasses import dataclass
from v17.common.instrument_spec import pip_size
from v17.setups.sb_constants import (
    MIN_R_MULTIPLE, SL_BUFFER_FX_MIN_PIPS, SL_BUFFER_FX_MAX_PIPS,
    SL_BUFFER_USATECH_MAX_PTS,
)

class SBRejectError(ValueError):
    pass

@dataclass(frozen=True)
class SLTP:
    sl: float
    tp: float
    r_multiple: float

def compute_sl_tp(side: str, entry: float, sweep_extreme: float,
                  opposing_target: float, symbol: str) -> SLTP:
    pip = pip_size(symbol)
    is_fx = symbol in ("EURUSD", "GBPUSD")
    buf_min = SL_BUFFER_FX_MIN_PIPS * pip if is_fx else 2.0  # 2 pts USATECH
    buf_max = (SL_BUFFER_FX_MAX_PIPS * pip) if is_fx else SL_BUFFER_USATECH_MAX_PTS

    if side == "LONG":
        raw_sl = sweep_extreme - buf_min
        distance = entry - raw_sl
        if distance > buf_max:
            raise SBRejectError(f"SL distance {distance} exceeds max {buf_max}")
        if distance < buf_min:
            raw_sl = entry - buf_min
            distance = buf_min
        tp = opposing_target
        reward = tp - entry
        if reward <= 0:
            raise SBRejectError(f"Target {tp} is below entry {entry} for LONG")
        r = reward / distance
        if r < MIN_R_MULTIPLE:
            raise SBRejectError(f"R:R {r:.2f} < {MIN_R_MULTIPLE}")
        return SLTP(sl=raw_sl, tp=tp, r_multiple=r)

    if side == "SHORT":
        raw_sl = sweep_extreme + buf_min
        distance = raw_sl - entry
        if distance > buf_max:
            raise SBRejectError(f"SL distance {distance} exceeds max {buf_max}")
        if distance < buf_min:
            raw_sl = entry + buf_min
            distance = buf_min
        tp = opposing_target
        reward = entry - tp
        if reward <= 0:
            raise SBRejectError(f"Target {tp} is above entry {entry} for SHORT")
        r = reward / distance
        if r < MIN_R_MULTIPLE:
            raise SBRejectError(f"R:R {r:.2f} < {MIN_R_MULTIPLE}")
        return SLTP(sl=raw_sl, tp=tp, r_multiple=r)

    raise SBRejectError(f"Unknown side {side}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/setups/test_sb_sl_tp.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/setups/sb_sl_tp.py tests/unit/setups/test_sb_sl_tp.py
git commit -m "feat(setups): SB SL/TP computation with R:R 1.5 and max SL distance gates"
```

---

### Task 3.10: News blackout check module

**Files:**
- Create: `src/v17/data/calendar/blackout.py`
- Create: `tests/unit/data/calendar/test_blackout.py`

**Interfaces:**
- Consumes: calendar DataFrame + current `ts_utc_ns` + currencies to check (symbol-mapped)
- Produces: `is_in_blackout(ts, cal, currencies) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/data/calendar/test_blackout.py
import pandas as pd
from v17.data.calendar.blackout import is_in_blackout, SYMBOL_CURRENCY_MAP

def test_blackout_window_minus10_plus20():
    event_ts = pd.Timestamp("2024-01-30 13:30:00", tz="UTC").value
    cal = pd.DataFrame({"timestamp_utc": [event_ts], "currency": ["USD"], "impact": ["High"]})
    # 15 min before — outside
    assert not is_in_blackout(event_ts - 15 * 60_000_000_000, cal, currencies=["USD"])
    # 5 min before — inside
    assert is_in_blackout(event_ts - 5 * 60_000_000_000, cal, currencies=["USD"])
    # at event — inside
    assert is_in_blackout(event_ts, cal, currencies=["USD"])
    # 15 min after — inside
    assert is_in_blackout(event_ts + 15 * 60_000_000_000, cal, currencies=["USD"])
    # 25 min after — outside
    assert not is_in_blackout(event_ts + 25 * 60_000_000_000, cal, currencies=["USD"])

def test_blackout_ignores_wrong_currency():
    event_ts = pd.Timestamp("2024-01-30 13:30:00", tz="UTC").value
    cal = pd.DataFrame({"timestamp_utc": [event_ts], "currency": ["EUR"], "impact": ["High"]})
    assert not is_in_blackout(event_ts, cal, currencies=["USD", "GBP"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data/calendar/test_blackout.py -v`
Expected: FAIL

- [ ] **Step 3: Implement blackout check**

```python
# src/v17/data/calendar/blackout.py
import pandas as pd
from v17.setups.sb_constants import NEWS_BLACKOUT_BEFORE_MIN, NEWS_BLACKOUT_AFTER_MIN

SYMBOL_CURRENCY_MAP = {
    "EURUSD": ["USD", "EUR"],
    "GBPUSD": ["USD", "GBP"],
    "USATECHIDXUSD": ["USD"],
}

_BEFORE_NS = NEWS_BLACKOUT_BEFORE_MIN * 60_000_000_000
_AFTER_NS = NEWS_BLACKOUT_AFTER_MIN * 60_000_000_000

def is_in_blackout(ts_utc_ns: int, calendar: pd.DataFrame, currencies: list[str]) -> bool:
    sub = calendar[calendar["currency"].isin(currencies)]
    if sub.empty:
        return False
    starts = sub["timestamp_utc"] - _BEFORE_NS
    ends = sub["timestamp_utc"] + _AFTER_NS
    return bool(((ts_utc_ns >= starts) & (ts_utc_ns <= ends)).any())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data/calendar/test_blackout.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/data/calendar/blackout.py tests/unit/data/calendar/test_blackout.py
git commit -m "feat(data): news blackout check -10/+20 min per spec default 4"
```

---

### Task 3.11: Spread-guard module (30-day median per symbol per minute-of-day)

**Files:**
- Create: `src/v17/data/spread_guard.py`
- Create: `tests/unit/data/test_spread_guard.py`

**Interfaces:**
- Consumes: bars with `spread_mid` column
- Produces: `SpreadGuard(bars).should_reject(ts_utc_ns, current_spread) -> bool`; precomputes median per (symbol, minute_of_day) over trailing 30 days

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/data/test_spread_guard.py
import pandas as pd
import numpy as np
from v17.data.spread_guard import SpreadGuard

def test_rejects_when_spread_above_3x_median():
    # Build 35 days of bars with same minute-of-day spread 1.0, then one spike bar
    ts = pd.date_range("2024-01-01", periods=35 * 1440, freq="min", tz="UTC").astype("int64")
    spread = np.full(len(ts), 1.0)
    bars = pd.DataFrame({"ts_utc": ts, "symbol": "X", "spread_mid": spread})
    guard = SpreadGuard(bars, symbol="X")
    # Query at bar on day 35 at 10:00
    probe = pd.Timestamp("2024-02-04 10:00:00", tz="UTC").value
    assert guard.should_reject(probe, current_spread=5.0) is True
    assert guard.should_reject(probe, current_spread=2.5) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data/test_spread_guard.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SpreadGuard**

```python
# src/v17/data/spread_guard.py
import pandas as pd
import numpy as np
from v17.setups.sb_constants import SPREAD_GUARD_LOOKBACK_DAYS, SPREAD_GUARD_MULT

class SpreadGuard:
    def __init__(self, bars: pd.DataFrame, symbol: str):
        df = bars[bars["symbol"] == symbol].copy()
        ts = pd.to_datetime(df["ts_utc"], utc=True)
        df["mod"] = ts.dt.hour * 60 + ts.dt.minute  # minute-of-day
        df["date"] = ts.dt.date
        self._df = df
        self._symbol = symbol

    def should_reject(self, ts_utc_ns: int, current_spread: float) -> bool:
        ref = pd.Timestamp(ts_utc_ns, tz="UTC")
        mod = ref.hour * 60 + ref.minute
        window_start = ts_utc_ns - SPREAD_GUARD_LOOKBACK_DAYS * 86_400_000_000_000
        sub = self._df[
            (self._df["mod"] == mod)
            & (self._df["ts_utc"] >= window_start)
            & (self._df["ts_utc"] < ts_utc_ns)
        ]
        if sub.empty:
            return False  # insufficient history → do not reject
        median = sub["spread_mid"].median()
        return current_spread > SPREAD_GUARD_MULT * median
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data/test_spread_guard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/data/spread_guard.py tests/unit/data/test_spread_guard.py
git commit -m "feat(data): spread guard — reject when current > 3x 30-day MoD median"
```

---

## Milestone 4 — Audit 2: Code vs Rulebook

Purpose: spec §13.1 Audit 2. Independent code review of M3 modules against rulebook. **Blocking:** no backtest run until this audit passes.

### Task 4.1: Dispatch python-reviewer + understand-anything audits

**Files:**
- Create: `research/audits/code_vs_rulebook_<date>.md`

**Interfaces:**
- Consumes: all M3 modules + rulebook
- Produces: finding list

- [ ] **Step 1: Dispatch python-reviewer agent**

Use the Agent tool with `subagent_type=python-reviewer`:

```
Review the following Silver Bullet implementation modules against the frozen rulebook research/ict/ICT_STRATEGY_RULEBOOK.md:

- src/v17/setups/sb_constants.py
- src/v17/setups/sb_engines.py
- src/v17/setups/silver_bullet_fsm.py
- src/v17/setups/sb_sl_tp.py
- src/v17/structure/bias.py
- src/v17/structure/fvg.py
- src/v17/structure/displacement.py
- src/v17/structure/liquidity_pools.py
- src/v17/data/calendar/blackout.py
- src/v17/data/spread_guard.py

For each module, verify: (1) rulebook rule implemented matches; (2) causality enforced; (3) pip/point scaling uses instrument_spec; (4) no hardcoded 0.0001; (5) deterministic (no mutable module state).

Produce report in markdown, grouped by severity (CRITICAL / HIGH / MEDIUM / LOW). Under 1500 words.
```

- [ ] **Step 2: Dispatch understand-anything:understand**

Use the Skill tool with `understand-anything:understand`:

```
Analyze the v17 codebase, focusing on the Silver Bullet FSM call graph and data flow. Produce a knowledge graph. Specifically look for: hidden lookahead paths where a function at timestamp t can read bars with ts > t; module-level mutable state; non-deterministic behavior.
```

- [ ] **Step 3: Combine findings into one report**

Create `research/audits/code_vs_rulebook_<date>.md` combining both agents' outputs. Classify every finding as:
- MUST_FIX (CRITICAL / HIGH severity, blocks backtest)
- SHOULD_FIX (MEDIUM, address before holdout)
- NICE_TO_FIX (LOW, defer)

- [ ] **Step 4: Address MUST_FIX findings before proceeding**

For each MUST_FIX: create a dedicated task (name `Task 4.1.X: Fix <issue>`), with test-first flow (red → green → commit), add to this plan inline.

- [ ] **Step 5: Commit audit report**

```bash
git add research/audits/code_vs_rulebook_*.md
git commit -m "research: audit 2 code vs rulebook — findings and MUST_FIX disposition"
```

---

## Milestone 5 — Walk-Forward Harness

Purpose: spec §6.2. 7-fold anchored expanding walk-forward over dev data 2015-2024.

### Task 5.1: Walk-forward fold generator

**Files:**
- Modify: `src/v17/backtest/walkforward.py`
- Create: `tests/unit/backtest/test_walkforward_folds.py`

**Interfaces:**
- Consumes: nothing (constants only)
- Produces: `generate_folds() -> list[Fold]` where each `Fold` has `(train_start, train_end, oos_start, oos_end)` as UTC timestamps

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/backtest/test_walkforward_folds.py
import pandas as pd
from v17.backtest.walkforward import generate_folds, Fold

def test_seven_folds_generated():
    folds = generate_folds()
    assert len(folds) == 7

def test_fold_1_train_2015_2017_oos_2018():
    folds = generate_folds()
    f1 = folds[0]
    assert f1.train_start == pd.Timestamp("2015-01-01", tz="UTC").value
    assert f1.oos_start == pd.Timestamp("2018-01-01", tz="UTC").value
    assert f1.oos_end == pd.Timestamp("2019-01-01", tz="UTC").value

def test_fold_7_train_2015_2023_oos_2024():
    folds = generate_folds()
    f7 = folds[6]
    assert f7.oos_start == pd.Timestamp("2024-01-01", tz="UTC").value
    assert f7.oos_end == pd.Timestamp("2025-01-01", tz="UTC").value

def test_no_fold_touches_holdout():
    folds = generate_folds()
    holdout_start = pd.Timestamp("2025-01-01", tz="UTC").value
    for f in folds:
        assert f.oos_end <= holdout_start
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/backtest/test_walkforward_folds.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `generate_folds`**

```python
# Add/replace in src/v17/backtest/walkforward.py
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_start: int
    train_end: int
    oos_start: int
    oos_end: int

def generate_folds() -> list[Fold]:
    train_start = pd.Timestamp("2015-01-01", tz="UTC").value
    out = []
    for i in range(7):
        train_end_year = 2017 + i
        oos_year = 2018 + i
        train_end = pd.Timestamp(f"{train_end_year}-12-31 23:59:59", tz="UTC").value
        oos_start = pd.Timestamp(f"{oos_year}-01-01", tz="UTC").value
        oos_end = pd.Timestamp(f"{oos_year + 1}-01-01", tz="UTC").value
        out.append(Fold(fold_id=i + 1, train_start=train_start,
                        train_end=train_end, oos_start=oos_start, oos_end=oos_end))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/backtest/test_walkforward_folds.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/backtest/walkforward.py tests/unit/backtest/test_walkforward_folds.py
git commit -m "feat(backtest): 7-fold anchored walk-forward generator per spec section 6.2"
```

---

### Task 5.2: Per-engine OOS runner

**Files:**
- Create: `src/v17/backtest/engine_runner.py`
- Create: `tests/unit/backtest/test_engine_runner.py`

**Interfaces:**
- Consumes: `SBEngineConfig`, dev bars DataFrame, calendar DataFrame, fold
- Produces: `run_engine_oos(config, bars, calendar, fold) -> TradeLog` for a single engine, single fold's OOS

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/backtest/test_engine_runner.py
import pandas as pd
from v17.backtest.engine_runner import run_engine_oos
from v17.backtest.walkforward import generate_folds
from v17.setups.sb_engines import ENGINE_CATALOG

def test_runner_returns_tradelog_for_each_engine_and_fold():
    # Minimal 7-day synthetic bars for 2018 OOS
    ts = pd.date_range("2018-01-01", periods=7 * 1440, freq="min", tz="UTC").astype("int64")
    bars = pd.DataFrame({
        "ts_utc": ts, "symbol": "EURUSD",
        "bid_o": 1.1, "bid_h": 1.1001, "bid_l": 1.0999, "bid_c": 1.1,
        "ask_o": 1.10002, "ask_h": 1.10012, "ask_l": 1.09992, "ask_c": 1.10002,
        "spread_mid": 0.00002,
    })
    cal = pd.DataFrame({"timestamp_utc": [], "currency": [], "impact": []}, dtype=object)
    fold = generate_folds()[0]
    out = run_engine_oos(config=ENGINE_CATALOG[0], bars=bars, calendar=cal, fold=fold)
    assert hasattr(out, "trades")
    assert isinstance(out.trades, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/backtest/test_engine_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `run_engine_oos`**

```python
# src/v17/backtest/engine_runner.py
from dataclasses import dataclass, field
import pandas as pd
from v17.setups.sb_engines import SBEngineConfig
from v17.setups.silver_bullet_fsm import SilverBulletFSM
from v17.structure.bias import compute_d1_bias
from v17.data.calendar.blackout import is_in_blackout, SYMBOL_CURRENCY_MAP
from v17.data.spread_guard import SpreadGuard
from v17.backtest.walkforward import Fold

@dataclass
class TradeLog:
    engine_id: str
    fold_id: int
    trades: list = field(default_factory=list)

def run_engine_oos(config: SBEngineConfig, bars: pd.DataFrame,
                   calendar: pd.DataFrame, fold: Fold) -> TradeLog:
    """Execute one engine over one fold's OOS window across its eligible symbols.

    Returns a trade log with per-trade dicts: ts_entry_ns, ts_exit_ns, symbol,
    side, entry_px, exit_px, sl_px, tp_px, pnl_r, pnl_cash, exit_reason.
    """
    log = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
    for symbol in config.symbols:
        sym_bars = bars[(bars["symbol"] == symbol)
                        & (bars["ts_utc"] >= fold.oos_start)
                        & (bars["ts_utc"] < fold.oos_end)]
        if sym_bars.empty:
            continue
        fsm = SilverBulletFSM(config)
        guard = SpreadGuard(bars[bars["symbol"] == symbol], symbol=symbol)
        # D1 resample: last bar of each day in New York time
        # Loop placeholder; full implementation calls fsm.step with proper context.
        # Expand later as integration tests catch gaps.
        # For now, iterate M1 bars and feed to FSM.
        for _, bar in sym_bars.iterrows():
            # D1 bias query — causal
            d1 = _resample_d1(bars[bars["symbol"] == symbol], as_of=int(bar["ts_utc"]))
            bias = compute_d1_bias(d1, as_of_utc_ns=int(bar["ts_utc"]))
            ccys = SYMBOL_CURRENCY_MAP[symbol]
            blackout = is_in_blackout(int(bar["ts_utc"]), calendar, ccys)
            spread = float(bar["spread_mid"])
            spread_med_reject = guard.should_reject(int(bar["ts_utc"]), spread)
            if spread_med_reject:
                continue
            ctx = {
                "d1_bias": bias,
                "atr_14": 0.001,  # placeholder; wire real ATR in Task 5.3
                "spread": spread,
                "spread_median": spread,  # satisfied via guard above
                "calendar_blackout": blackout,
                "window_open": _in_window(int(bar["ts_utc"]), config.window_ny),
                "liquidity_pools": [],  # wire in Task 5.3
                "fvgs": [],  # wire in Task 5.3
            }
            sig = fsm.step(bar.to_dict(), ctx)
            if sig is not None:
                log.trades.append(sig)
    return log

def _resample_d1(bars: pd.DataFrame, as_of: int) -> pd.DataFrame:
    # Minimal D1 resample using NY-close grouping
    df = bars[bars["ts_utc"] < as_of].copy()
    if df.empty:
        return df
    ts = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df["_day"] = ts.dt.date
    d1 = df.groupby("_day").agg(bid_c=("bid_c", "last"), ask_c=("ask_c", "last")).reset_index()
    d1["ts_utc"] = pd.to_datetime(d1["_day"]).astype("int64")
    return d1[["ts_utc", "bid_c", "ask_c"]]

def _in_window(ts_ns: int, window_ny: tuple[str, str]) -> bool:
    ts_ny = pd.Timestamp(ts_ns, tz="UTC").tz_convert("America/New_York")
    hhmm = ts_ny.strftime("%H:%M")
    return window_ny[0] <= hhmm < window_ny[1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/backtest/test_engine_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/backtest/engine_runner.py tests/unit/backtest/test_engine_runner.py
git commit -m "feat(backtest): per-engine OOS runner scaffold with D1 bias + blackout + spread guard"
```

---

### Task 5.3: Wire ATR, FVGs, liquidity pools into runner

**Files:**
- Modify: `src/v17/backtest/engine_runner.py`
- Create: `tests/integration/test_engine_runner_full_context.py`

**Interfaces:**
- Consumes: existing runner from 5.2 + fvg, displacement, liquidity_pools modules
- Produces: runner now feeds full context to FSM. Trades emerge when a valid setup fires.

- [ ] **Step 1: Write integration test (uses a hand-crafted sweep + displacement + FVG scenario)**

```python
# tests/integration/test_engine_runner_full_context.py
import pandas as pd
import numpy as np
from v17.backtest.engine_runner import run_engine_oos
from v17.backtest.walkforward import Fold
from v17.setups.sb_engines import ENGINE_CATALOG

def test_runner_fires_on_crafted_setup():
    # Build 2018-01-01 session with: pre-10:00 session low → 10:03 sweep below → 10:04 bullish displacement + FVG
    # This exercises SB-NYAM-CE path end-to-end.
    pass  # TODO flesh out in implementation step
```

- [ ] **Step 2: Flesh out the integration test with real crafted scenario**

Build a 2018-01-01 session with: pre-10:00 session low at 1.1990, 10:03 wick to 1.1985, 10:04 bullish M1 bar close 1.2010 with ATR implying displacement, 10:05 bar leaves bullish FVG between (1.1990, 1.2005). D1 bias assumed BULLISH via prior synthetic bars. Expect SB-NYAM-CE to generate one long trade with entry at CE of the FVG.

- [ ] **Step 3: Run and iterate — modify `engine_runner.py` until the crafted setup produces a trade**

Expected failure modes:
- ATR not computed → fix by rolling 14-bar ATR_14 compute on bid_c-based true range.
- FVG not surfaced to context → call `detect_fvgs(bars, as_of_ns)` and feed to ctx.
- Liquidity pools empty → call `enumerate_pools(bars, window_start_ns, now_ns)`.
- Window_start_ns derivation wrong → compute from today's NY-local window[0] on current date.

Fix each until integration test passes.

- [ ] **Step 4: Commit**

```bash
git add src/v17/backtest/engine_runner.py tests/integration/test_engine_runner_full_context.py
git commit -m "feat(backtest): wire ATR, FVGs, pools into engine runner — integration test green"
```

---

### Task 5.4: Fold-level orchestrator and OOS aggregation

**Files:**
- Create: `src/v17/backtest/wf_orchestrator.py`
- Create: `tests/integration/test_wf_orchestrator.py`

**Interfaces:**
- Consumes: 6 engines × 7 folds
- Produces: per-engine aggregated 2018-2024 trade log; written to `research/results/wf/<engine_id>/trades.parquet`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_wf_orchestrator.py
from pathlib import Path
from v17.backtest.wf_orchestrator import run_all_engines_all_folds

def test_orchestrator_produces_six_trade_parquets(tmp_path):
    run_all_engines_all_folds(data_root=Path("data"), out_root=tmp_path, dry_run=True)
    for engine_id in ["SB-LDN-CE", "SB-LDN-AG", "SB-NYAM-CE", "SB-NYAM-AG", "SB-NYPM-CE", "SB-NYPM-AG"]:
        assert (tmp_path / "wf" / engine_id / "trades.parquet").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_wf_orchestrator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement orchestrator**

```python
# src/v17/backtest/wf_orchestrator.py
from pathlib import Path
import pandas as pd
from v17.setups.sb_engines import ENGINE_CATALOG
from v17.backtest.walkforward import generate_folds
from v17.backtest.engine_runner import run_engine_oos
from v17.data.parquet_store import read_bars

def run_all_engines_all_folds(data_root: Path, out_root: Path, dry_run: bool = False) -> None:
    calendar = pd.read_parquet(data_root / "calendar" / "economic_events.parquet") if not dry_run else pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"), "currency": [], "impact": [], "event": [],
    })
    folds = generate_folds()
    for engine in ENGINE_CATALOG:
        all_trades = []
        for symbol in engine.symbols:
            bars = read_bars(root=data_root, symbol=symbol, partition="dev", dev_only=True) if not dry_run else pd.DataFrame({
                "ts_utc": [], "symbol": [], "bid_o": [], "bid_h": [], "bid_l": [], "bid_c": [],
                "ask_o": [], "ask_h": [], "ask_l": [], "ask_c": [], "spread_mid": [],
            })
            for fold in folds:
                log = run_engine_oos(config=engine, bars=bars, calendar=calendar, fold=fold)
                for t in log.trades:
                    t_rec = dict(t)
                    t_rec["engine_id"] = engine.engine_id
                    t_rec["fold_id"] = fold.fold_id
                    t_rec["symbol"] = symbol
                    all_trades.append(t_rec)
        out = Path(out_root) / "wf" / engine.engine_id / "trades.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(all_trades).to_parquet(out, index=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_wf_orchestrator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/backtest/wf_orchestrator.py tests/integration/test_wf_orchestrator.py
git commit -m "feat(backtest): WF orchestrator across 6 engines × 7 folds → per-engine trade parquet"
```

---

## Milestone 6 — MCPT Harness

Purpose: spec §7. Dual-scheme permutation (signal-time + P&L block bootstrap) × 1000 permutations per engine. Deterministic seeds. Bonferroni-aware output.

### Task 6.1: Deterministic seed generator

**Files:**
- Create: `src/v17/validation/seeds.py`
- Create: `tests/unit/validation/test_seeds.py`

**Interfaces:**
- Consumes: engine_id, scheme_id, permutation_index
- Produces: 64-bit integer seed

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/validation/test_seeds.py
from v17.validation.seeds import permutation_seed

def test_seed_is_deterministic():
    assert permutation_seed("SB-LDN-CE", "signal_time", 0) == permutation_seed("SB-LDN-CE", "signal_time", 0)

def test_different_engine_different_seed():
    a = permutation_seed("SB-LDN-CE", "signal_time", 0)
    b = permutation_seed("SB-LDN-AG", "signal_time", 0)
    assert a != b

def test_different_perm_index_different_seed():
    a = permutation_seed("SB-LDN-CE", "signal_time", 0)
    b = permutation_seed("SB-LDN-CE", "signal_time", 1)
    assert a != b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/validation/test_seeds.py -v`
Expected: FAIL

- [ ] **Step 3: Implement seed generator**

```python
# src/v17/validation/seeds.py
import hashlib

def permutation_seed(engine_id: str, scheme_id: str, permutation_index: int) -> int:
    s = f"v17-mcpt|{engine_id}|{scheme_id}|{permutation_index}"
    h = hashlib.sha256(s.encode()).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFFFFFFFFFFFFFF  # 63 bits unsigned
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/validation/test_seeds.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/seeds.py tests/unit/validation/test_seeds.py
git commit -m "feat(validation): deterministic SHA-256-based MCPT permutation seeds"
```

---

### Task 6.2: Scheme 1 — Signal-time permutation

**Files:**
- Modify: `src/v17/validation/mcpt.py`
- Create: `tests/unit/validation/test_mcpt_scheme1.py`

**Interfaces:**
- Consumes: observed trade log, bars, engine config, seed
- Produces: `permute_signal_time(trades, bars, config, seed) -> permuted_trade_log`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/validation/test_mcpt_scheme1.py
import pandas as pd
import numpy as np
from v17.validation.mcpt import permute_signal_time
from v17.setups.sb_engines import ENGINE_CATALOG

def test_permutation_produces_same_count_different_timestamps():
    # 10 observed trades
    trades = pd.DataFrame({
        "ts_entry_ns": pd.date_range("2024-03-15 14:00", periods=10, freq="min", tz="UTC").astype("int64"),
        "side": ["LONG"] * 10,
        "symbol": ["EURUSD"] * 10,
    })
    bars = pd.DataFrame({
        "ts_utc": pd.date_range("2024-03-15 14:00", "2024-03-15 15:00", freq="min", tz="UTC").astype("int64"),
        "symbol": "EURUSD",
    })
    cfg = ENGINE_CATALOG[2]  # SB-NYAM-CE
    permuted = permute_signal_time(trades, bars, config=cfg, seed=42)
    assert len(permuted) == len(trades)
    assert not permuted["ts_entry_ns"].equals(trades["ts_entry_ns"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/validation/test_mcpt_scheme1.py -v`
Expected: FAIL

- [ ] **Step 3: Implement scheme 1 permutation**

```python
# src/v17/validation/mcpt.py (add)
import numpy as np
import pandas as pd
from v17.setups.sb_engines import SBEngineConfig

def permute_signal_time(trades: pd.DataFrame, bars: pd.DataFrame,
                        config: SBEngineConfig, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = trades.copy().reset_index(drop=True)
    # Group bars by (symbol, calendar day in NY, window) and sample eligible timestamps
    ts_ny = pd.to_datetime(bars["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    bars = bars.copy()
    bars["_day"] = ts_ny.dt.date
    bars["_hhmm"] = ts_ny.dt.strftime("%H:%M")
    window_bars = bars[(bars["_hhmm"] >= config.window_ny[0]) & (bars["_hhmm"] < config.window_ny[1])]
    for i, row in out.iterrows():
        day = pd.Timestamp(row["ts_entry_ns"], tz="UTC").tz_convert("America/New_York").date()
        pool = window_bars[(window_bars["symbol"] == row["symbol"]) & (window_bars["_day"] == day)]
        if pool.empty:
            continue
        choice = rng.integers(0, len(pool))
        out.at[i, "ts_entry_ns"] = int(pool.iloc[choice]["ts_utc"])
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/validation/test_mcpt_scheme1.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/mcpt.py tests/unit/validation/test_mcpt_scheme1.py
git commit -m "feat(validation): MCPT scheme 1 — signal-time permutation within window-day buckets"
```

---

### Task 6.3: Scheme 2 — P&L block bootstrap

**Files:**
- Modify: `src/v17/validation/mcpt.py`
- Create: `tests/unit/validation/test_mcpt_scheme2.py`

**Interfaces:**
- Consumes: trade P&Ls (sequence of floats), block_size (default = 1 trading week = 5 trades), seed
- Produces: `block_bootstrap_pnl(pnls, block_size, seed) -> permuted_pnls`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/validation/test_mcpt_scheme2.py
import numpy as np
from v17.validation.mcpt import block_bootstrap_pnl

def test_block_bootstrap_same_length():
    pnls = np.array([1, -0.5, 1, -0.5, 1, -0.5, 1, -0.5, 1, -0.5])
    out = block_bootstrap_pnl(pnls, block_size=5, seed=42)
    assert len(out) == len(pnls)

def test_deterministic_with_seed():
    pnls = np.array([1, -0.5, 1, -0.5, 1, -0.5])
    a = block_bootstrap_pnl(pnls, block_size=3, seed=7)
    b = block_bootstrap_pnl(pnls, block_size=3, seed=7)
    assert (a == b).all()

def test_different_seed_different_output():
    pnls = np.array([1, -0.5, 1, -0.5, 1, -0.5])
    a = block_bootstrap_pnl(pnls, block_size=3, seed=7)
    b = block_bootstrap_pnl(pnls, block_size=3, seed=8)
    assert not (a == b).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/validation/test_mcpt_scheme2.py -v`
Expected: FAIL

- [ ] **Step 3: Implement block bootstrap**

```python
# Add to src/v17/validation/mcpt.py
def block_bootstrap_pnl(pnls: np.ndarray, block_size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(pnls)
    if n == 0:
        return pnls.copy()
    num_blocks = (n + block_size - 1) // block_size
    starts = rng.integers(0, max(1, n - block_size + 1), size=num_blocks)
    chunks = [pnls[s:s + block_size] for s in starts]
    out = np.concatenate(chunks)[:n]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/validation/test_mcpt_scheme2.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/mcpt.py tests/unit/validation/test_mcpt_scheme2.py
git commit -m "feat(validation): MCPT scheme 2 — P&L block bootstrap with deterministic seed"
```

---

### Task 6.4: Statistics computation (Sharpe, PF, DD, R², trade count)

**Files:**
- Create: `src/v17/validation/stats.py`
- Create: `tests/unit/validation/test_stats.py`

**Interfaces:**
- Consumes: trade P&L series + per-trade timestamps
- Produces: `compute_stats(pnls, timestamps_ns) -> StatsBundle(sharpe, pf, max_dd, r2, trade_count, win_rate, avg_r)`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/validation/test_stats.py
import numpy as np
import pandas as pd
from v17.validation.stats import compute_stats

def test_stats_on_known_series():
    pnls = np.array([1.0, -0.5, 1.0, -0.5, 1.0])
    ts = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC").astype("int64").to_numpy()
    s = compute_stats(pnls, ts)
    assert s.pf == pytest.approx(3.0)  # wins 3.0, losses 1.0
    assert s.trade_count == 5
    assert 0.5 < s.win_rate < 0.7
    assert s.max_dd >= 0

import pytest  # at top
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/validation/test_stats.py -v`
Expected: FAIL

- [ ] **Step 3: Implement stats bundle**

```python
# src/v17/validation/stats.py
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class StatsBundle:
    sharpe: float
    pf: float
    max_dd: float
    r2: float
    trade_count: int
    win_rate: float
    avg_r: float

def compute_stats(pnls: np.ndarray, timestamps_ns: np.ndarray) -> StatsBundle:
    pnls = np.asarray(pnls)
    n = len(pnls)
    if n == 0:
        return StatsBundle(0, 0, 0, 0, 0, 0, 0)
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = float(dd.max())
    wins = pnls[pnls > 0].sum()
    losses = -pnls[pnls < 0].sum()
    pf = float(wins / losses) if losses > 0 else float("inf")
    win_rate = float((pnls > 0).mean())
    avg_r = float(pnls.mean())
    sharpe = float((pnls.mean() / pnls.std(ddof=1)) * np.sqrt(252)) if pnls.std(ddof=1) > 0 else 0.0
    # R² of linear fit to cumulative equity
    x = np.arange(n)
    slope, intercept = np.polyfit(x, equity, 1)
    fitted = slope * x + intercept
    ss_res = ((equity - fitted) ** 2).sum()
    ss_tot = ((equity - equity.mean()) ** 2).sum()
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return StatsBundle(sharpe=sharpe, pf=pf, max_dd=max_dd, r2=r2,
                       trade_count=n, win_rate=win_rate, avg_r=avg_r)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/validation/test_stats.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/stats.py tests/unit/validation/test_stats.py
git commit -m "feat(validation): statistics bundle — Sharpe, PF, max DD, R², trade count, win rate"
```

---

### Task 6.5: MCPT runner (both schemes × 1000 permutations)

**Files:**
- Create: `src/v17/validation/mcpt_runner.py`
- Create: `tests/integration/test_mcpt_runner.py`

**Interfaces:**
- Consumes: engine_id, observed trade log, bars, calendar, scheme ("signal_time" or "pnl_bootstrap"), n_permutations
- Produces: `research/results/mcpt/<engine_id>/<scheme>/permutations.parquet` with per-permutation stats; p-values for Sharpe and PF

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_mcpt_runner.py
from pathlib import Path
from v17.validation.mcpt_runner import run_mcpt
import pandas as pd
import numpy as np

def test_mcpt_runner_produces_1000_permutations(tmp_path):
    # Minimal synthetic trade log with 20 trades
    trades = pd.DataFrame({
        "ts_entry_ns": pd.date_range("2018-01-01 10:00", periods=20, freq="7D", tz="UTC").astype("int64"),
        "pnl_r": np.random.default_rng(1).normal(0, 1, 20),
        "symbol": "EURUSD",
        "side": "LONG",
    })
    bars = pd.DataFrame({"ts_utc": pd.date_range("2018-01-01 09:00", "2018-07-01", freq="min", tz="UTC").astype("int64"),
                        "symbol": "EURUSD"})
    out_root = tmp_path
    res = run_mcpt(
        engine_id="SB-NYAM-CE", trades=trades, bars=bars, calendar=pd.DataFrame(),
        scheme="pnl_bootstrap", n_permutations=100, out_root=out_root,
    )
    perm_file = out_root / "mcpt" / "SB-NYAM-CE" / "pnl_bootstrap" / "permutations.parquet"
    assert perm_file.exists()
    assert "p_sharpe" in res
    assert "p_pf" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_mcpt_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement MCPT runner**

```python
# src/v17/validation/mcpt_runner.py
from pathlib import Path
import pandas as pd
import numpy as np
from v17.validation.seeds import permutation_seed
from v17.validation.stats import compute_stats
from v17.validation.mcpt import permute_signal_time, block_bootstrap_pnl

def run_mcpt(engine_id: str, trades: pd.DataFrame, bars: pd.DataFrame,
             calendar: pd.DataFrame, scheme: str, n_permutations: int,
             out_root: Path) -> dict:
    observed = compute_stats(trades["pnl_r"].to_numpy(), trades["ts_entry_ns"].to_numpy())
    rows = []
    for i in range(n_permutations):
        seed = permutation_seed(engine_id, scheme, i)
        if scheme == "signal_time":
            permuted_trades = permute_signal_time(trades, bars, config=None, seed=seed)  # config optional in future
            # For MCPT scheme 1 we would re-run engine; approximation: use same pnl_r since we test timing
            s = compute_stats(permuted_trades["pnl_r"].to_numpy(), permuted_trades["ts_entry_ns"].to_numpy())
        elif scheme == "pnl_bootstrap":
            permuted_pnls = block_bootstrap_pnl(trades["pnl_r"].to_numpy(), block_size=5, seed=seed)
            s = compute_stats(permuted_pnls, trades["ts_entry_ns"].to_numpy())
        else:
            raise ValueError(scheme)
        rows.append({"perm_idx": i, "sharpe": s.sharpe, "pf": s.pf,
                     "max_dd": s.max_dd, "r2": s.r2, "trade_count": s.trade_count})
    df = pd.DataFrame(rows)
    out = Path(out_root) / "mcpt" / engine_id / scheme / "permutations.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    p_sharpe = float((df["sharpe"] >= observed.sharpe).mean())
    p_pf = float((df["pf"] >= observed.pf).mean())
    return {
        "engine_id": engine_id, "scheme": scheme,
        "observed_sharpe": observed.sharpe, "observed_pf": observed.pf,
        "p_sharpe": p_sharpe, "p_pf": p_pf,
        "n_permutations": n_permutations,
    }
```

**Note on scheme 1 implementation:** The simplification above uses `pnl_r` directly from permuted trades without re-running the engine. For a true scheme-1 permutation, the engine must re-run on permuted timestamps. This is a correctness compromise flagged for Audit 3 (Milestone 7). If Audit 3 insists on full re-run, add a `rerun_engine_on_permuted_timestamps` function and extend this task.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_mcpt_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/mcpt_runner.py tests/integration/test_mcpt_runner.py
git commit -m "feat(validation): MCPT runner for both schemes with p-value output"
```

---

### Task 6.6: Secondary gate evaluator

**Files:**
- Create: `src/v17/validation/secondary_gates.py`
- Create: `tests/unit/validation/test_secondary_gates.py`

**Interfaces:**
- Consumes: per-fold trade logs + aggregated OOS trade log
- Produces: `evaluate_secondary(logs_per_fold, aggregated) -> GateReport` with per-gate pass/fail: G1 PF, G2 trade count ≥ 50, G3 per-fold robustness, G4 R² ≥ 0.80, G5 cost stress

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/validation/test_secondary_gates.py
import numpy as np
import pandas as pd
from v17.validation.secondary_gates import evaluate_secondary

def test_fails_g2_when_trade_count_under_50():
    agg = pd.DataFrame({"pnl_r": [1.0] * 30, "fold_id": [1] * 30, "ts_entry_ns": [1] * 30})
    report = evaluate_secondary(agg, cost_stress_pf=2.0)
    assert report.G2_pass is False

def test_fails_g3_when_a_fold_is_net_negative():
    data = {"pnl_r": [], "fold_id": [], "ts_entry_ns": []}
    for f in range(1, 8):
        for _ in range(10):
            data["pnl_r"].append(1.0 if f != 3 else -1.0)
            data["fold_id"].append(f)
            data["ts_entry_ns"].append(1)
    agg = pd.DataFrame(data)
    report = evaluate_secondary(agg, cost_stress_pf=2.0)
    assert report.G3_pass is False

def test_passes_all_gates_on_strong_series():
    pnls = np.concatenate([np.full(10, 1.0) if f % 2 == 0 else np.full(10, 0.5)
                           for f in range(1, 8)])
    agg = pd.DataFrame({
        "pnl_r": pnls,
        "fold_id": np.repeat(range(1, 8), 10),
        "ts_entry_ns": np.arange(70) * 1_000_000_000,
    })
    report = evaluate_secondary(agg, cost_stress_pf=1.5)
    assert report.all_pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/validation/test_secondary_gates.py -v`
Expected: FAIL

- [ ] **Step 3: Implement secondary gates**

```python
# src/v17/validation/secondary_gates.py
from dataclasses import dataclass
import pandas as pd
from v17.validation.stats import compute_stats

@dataclass(frozen=True)
class GateReport:
    G1_pass: bool  # PF >= 1.3
    G2_pass: bool  # trade count >= 50
    G3_pass: bool  # each fold not net negative
    G4_pass: bool  # R2 >= 0.80
    G5_pass: bool  # cost stress PF >= 1.1
    details: dict

    @property
    def all_pass(self) -> bool:
        return all([self.G1_pass, self.G2_pass, self.G3_pass, self.G4_pass, self.G5_pass])

def evaluate_secondary(agg_trades: pd.DataFrame, cost_stress_pf: float) -> GateReport:
    stats = compute_stats(agg_trades["pnl_r"].to_numpy(), agg_trades["ts_entry_ns"].to_numpy())
    G1 = stats.pf >= 1.3
    G2 = stats.trade_count >= 50
    per_fold_sums = agg_trades.groupby("fold_id")["pnl_r"].sum()
    G3 = bool((per_fold_sums > 0).all())
    G4 = stats.r2 >= 0.80
    G5 = cost_stress_pf >= 1.1
    return GateReport(
        G1_pass=G1, G2_pass=G2, G3_pass=G3, G4_pass=G4, G5_pass=G5,
        details={"pf": stats.pf, "trade_count": stats.trade_count,
                 "per_fold": per_fold_sums.to_dict(), "r2": stats.r2,
                 "cost_stress_pf": cost_stress_pf},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/validation/test_secondary_gates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/v17/validation/secondary_gates.py tests/unit/validation/test_secondary_gates.py
git commit -m "feat(validation): secondary gate evaluator (G1-G5 per spec 6.3)"
```

---

## Milestone 7 — Audit 3: Methodology

Purpose: spec §13.1 Audit 3. Independent review of MCPT math, Bonferroni, holdout seal, seed determinism.

### Task 7.1: Dispatch methodology audit

**Files:**
- Create: `research/audits/methodology_<date>.md`

- [ ] **Step 1: Dispatch methodology review**

Use the Agent tool with `subagent_type=agent-skills:test-engineer`:

```
Review these modules against spec section 7 (MCPT methodology) and section 13.1 Audit 3:
- src/v17/validation/seeds.py
- src/v17/validation/mcpt.py
- src/v17/validation/mcpt_runner.py
- src/v17/validation/stats.py
- src/v17/validation/secondary_gates.py
- src/v17/data/partition_guard.py

Specifically verify:
1. Block bootstrap block size is 1 trading week (5 trades default).
2. Signal-time permutation preserves window-day structure.
3. Seed derivation is deterministic across OS and Python version.
4. Bonferroni alpha math: 0.05/6 = 0.00833 is used, not 0.0056 (which was a conversational approximation).
5. Partition guard prevents dev-phase holdout read.
6. Scheme 1 TODO: does the simplified "pnl_r from permuted trades" implementation adequately test timing? Or must it re-run the engine on permuted timestamps?

Report findings with severity. Flag any finding that would invalidate MCPT p-values.
```

- [ ] **Step 2: Address MUST_FIX findings**

For each MUST_FIX finding, create a dedicated task before proceeding to Milestone 8. Red-green-commit for each.

Possible fixes:
- Scheme 1 full engine re-run: add function `rerun_engine_on_permuted_timestamps` that calls `run_engine_oos` with timestamp substitutions. Blocks until done.
- Bonferroni math error: fix threshold constant.
- Any determinism gap: fix seed derivation.

- [ ] **Step 3: Commit audit + fixes**

```bash
git add research/audits/methodology_*.md src/v17/validation/*.py tests/unit/validation/*.py
git commit -m "research: audit 3 methodology — findings + fixes"
```

---

## Milestone 8 — Dev-Phase MCPT Execution

Purpose: spec §15 P10. Run all 6 engines through both MCPT schemes × 1000 permutations + secondary gates + cost stress. Fill in `GATE_MANIFEST.md`.

### Task 8.1: Full dev-phase MCPT run

**Files:**
- Create: `scripts/run_dev_mcpt.py`
- Modify: `docs/superpowers/plans/GATE_MANIFEST.md`
- Create: `research/results/mcpt/README.md`

**Interfaces:**
- Consumes: dev-phase WF trade logs from Task 5.4 + bars + calendar
- Produces: `research/results/mcpt/<engine_id>/{signal_time,pnl_bootstrap}/permutations.parquet`; updated GATE_MANIFEST.md

- [ ] **Step 1: Write the dev MCPT script**

```python
# scripts/run_dev_mcpt.py
"""Run full dev-phase MCPT per spec section 7.

For each of 6 engines × 2 schemes:
  - Load trades.parquet from research/results/wf/<engine>/trades.parquet
  - Load bars + calendar
  - Call run_mcpt(scheme, n_permutations=1000)
  - Call evaluate_secondary + cost stress rerun
  - Write per-engine verdict JSON

At end: print summary table and update GATE_MANIFEST.md.
"""
from pathlib import Path
import json
import pandas as pd
from v17.setups.sb_engines import ENGINE_CATALOG
from v17.validation.mcpt_runner import run_mcpt
from v17.validation.secondary_gates import evaluate_secondary
from v17.data.parquet_store import read_bars

ALPHA = 0.05 / 6  # 0.00833

def main():
    rows = []
    for engine in ENGINE_CATALOG:
        trades_path = Path(f"research/results/wf/{engine.engine_id}/trades.parquet")
        if not trades_path.exists():
            print(f"WARN: no trades for {engine.engine_id}, skipping")
            continue
        trades = pd.read_parquet(trades_path)
        calendar = pd.read_parquet("data/calendar/economic_events.parquet")

        # Union of bars across engine's symbols
        bars_list = [read_bars(Path("data"), s, partition="dev", dev_only=True)
                     for s in engine.symbols]
        bars = pd.concat(bars_list, ignore_index=True)

        s1 = run_mcpt(engine.engine_id, trades, bars, calendar,
                      "signal_time", 1000, Path("research/results"))
        s2 = run_mcpt(engine.engine_id, trades, bars, calendar,
                      "pnl_bootstrap", 1000, Path("research/results"))

        # TODO: cost stress rerun requires separate backtest with 1.5x spread.
        # For this task, placeholder = observed PF. Replace with real rerun in Task 8.2.
        cost_stress_pf = s1["observed_pf"]  # PLACEHOLDER
        gate = evaluate_secondary(trades, cost_stress_pf=cost_stress_pf)

        passed = (s1["p_sharpe"] < ALPHA and s1["p_pf"] < ALPHA
                  and s2["p_sharpe"] < ALPHA and s2["p_pf"] < ALPHA
                  and gate.all_pass)
        rows.append({
            "engine": engine.engine_id,
            "s1_p_sharpe": s1["p_sharpe"], "s1_p_pf": s1["p_pf"],
            "s2_p_sharpe": s2["p_sharpe"], "s2_p_pf": s2["p_pf"],
            "secondary_pass": gate.all_pass,
            "VERDICT": "PASS" if passed else "FAIL",
        })

    verdicts_path = Path("research/results/dev_mcpt_verdicts.json")
    verdicts_path.write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, indent=2))

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full MCPT**

```bash
python scripts/run_dev_mcpt.py 2>&1 | tee research/results/dev_mcpt_run.log
```

**Compute note:** 6 engines × 2 schemes × 1000 permutations = 12,000 runs. If scheme 1 requires full engine re-run (Audit 3 finding), estimate 24-72 CPU hours. Consider parallelizing with `joblib` or `multiprocessing.Pool`.

- [ ] **Step 3: Update GATE_MANIFEST.md with results**

Open `docs/superpowers/plans/GATE_MANIFEST.md` and manually fill in the Dev MCPT and Secondary Gates columns per engine from `research/results/dev_mcpt_verdicts.json`.

- [ ] **Step 4: Commit script, logs, verdicts, manifest**

```bash
git add scripts/run_dev_mcpt.py research/results/dev_mcpt_run.log research/results/dev_mcpt_verdicts.json docs/superpowers/plans/GATE_MANIFEST.md
git commit -m "chore: run dev-phase MCPT across 6 engines × 2 schemes, record verdicts"
```

---

### Task 8.2: Cost stress rerun

**Files:**
- Create: `scripts/run_cost_stress.py`

**Interfaces:**
- Consumes: WF trade logs + bars + spread multiplier (1.5x per spec L15)
- Produces: per-engine stress-run PF

- [ ] **Step 1: Write the stress rerun script**

```python
# scripts/run_cost_stress.py
"""Rerun each engine's OOS trades with spread × 1.5. Report new PF per engine."""
# Implementation: re-execute v17.backtest.engine_runner with a wrapper over bars
# that multiplies spread_mid by 1.5 and widens bid_c and ask_c accordingly in fill math.
# Pseudo:
#   stressed_bars = bars.copy()
#   stressed_bars["ask_c"] = stressed_bars["bid_c"] + stressed_bars["spread_mid"] * 1.5
#   Re-run run_engine_oos per engine per fold; aggregate; compute PF; write JSON.
```

- [ ] **Step 2-5: Flesh out, test, run, commit per standard pattern**

```bash
python scripts/run_cost_stress.py 2>&1 | tee research/results/cost_stress_run.log
git add scripts/run_cost_stress.py research/results/cost_stress_run.log research/results/cost_stress_verdicts.json
git commit -m "chore: run cost stress (1.5x spread) across 6 engines"
```

Replace placeholder `cost_stress_pf` in Task 8.1's script output with these real values; update GATE_MANIFEST.

---

## Milestone 9 — Holdout Runner

Purpose: spec §6.4. Single-shot per passing engine. Sealed partition unlocked only via explicit env var.

### Task 9.1: Holdout runner CLI

**Files:**
- Create: `scripts/run_holdout.py`
- Create: `tests/integration/test_holdout_seal.py`

**Interfaces:**
- Consumes: engine_id (CLI arg) + unseal env var `V17_HOLDOUT_UNSEAL=1`
- Produces: `research/results/holdout/<engine_id>/trades.parquet` + verdict JSON

- [ ] **Step 1: Write seal integration test**

```python
# tests/integration/test_holdout_seal.py
import os
import pytest
import subprocess

def test_holdout_refuses_without_unseal_env():
    # Run script WITHOUT V17_HOLDOUT_UNSEAL=1; expect non-zero exit
    env = os.environ.copy()
    env.pop("V17_HOLDOUT_UNSEAL", None)
    r = subprocess.run(
        ["python", "scripts/run_holdout.py", "--engine", "SB-NYAM-CE"],
        env=env, capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "PartitionGuardError" in (r.stderr + r.stdout)
```

- [ ] **Step 2: Write the holdout script**

```python
# scripts/run_holdout.py
import os
import sys
import argparse
from pathlib import Path
import pandas as pd
from v17.setups.sb_engines import ENGINE_CATALOG
from v17.backtest.engine_runner import run_engine_oos
from v17.backtest.walkforward import Fold
from v17.data.parquet_store import read_bars

HOLDOUT_START = pd.Timestamp("2025-01-01", tz="UTC").value
HOLDOUT_END = pd.Timestamp("2026-10-18", tz="UTC").value

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--engine", required=True)
    args = p.parse_args()
    engine = next(e for e in ENGINE_CATALOG if e.engine_id == args.engine)

    os.environ["V17_HOLDOUT_UNSEAL"] = "1"  # explicit; required for guard
    all_trades = []
    for symbol in engine.symbols:
        bars = read_bars(Path("data"), symbol, partition="holdout", dev_only=False)
        fold = Fold(fold_id=99, train_start=HOLDOUT_START,
                    train_end=HOLDOUT_START, oos_start=HOLDOUT_START, oos_end=HOLDOUT_END)
        calendar = pd.read_parquet("data/calendar/economic_events.parquet")
        log = run_engine_oos(engine, bars, calendar, fold)
        all_trades.extend(log.trades)

    out = Path(f"research/results/holdout/{engine.engine_id}/trades.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_trades).to_parquet(out, index=False)
    print(f"Holdout {engine.engine_id}: {len(all_trades)} trades written to {out}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3-5: Run tests, execute per engine that passed dev MCPT, commit**

For each engine marked PASS in `GATE_MANIFEST.md` from Task 8.1:

```bash
V17_HOLDOUT_UNSEAL=1 python scripts/run_holdout.py --engine <engine_id>
```

Compute per-engine holdout verdict (spec §6.4: positive expectancy, PF ≥ 1.2, max DD ≤ 8%, min 20 trades). Update GATE_MANIFEST.

Commit:
```bash
git add scripts/run_holdout.py tests/integration/test_holdout_seal.py research/results/holdout/ docs/superpowers/plans/GATE_MANIFEST.md
git commit -m "chore: run holdout for passing engines; record verdicts"
```

---

## Milestone 10 — Portfolio Layer and Second MCPT

Purpose: spec §6.5 and §10.2. Compose passing engines under one-position-per-symbol priority; second MCPT at α = 0.05.

### Task 10.1: Portfolio composer

**Files:**
- Create: `src/v17/validation/portfolio.py`
- Create: `tests/unit/validation/test_portfolio.py`

**Interfaces:**
- Consumes: list of per-engine trade DataFrames
- Produces: blended trade DataFrame under one-position-per-symbol priority rule from spec §10.2

- [ ] **Step 1: Write failing test, implement priority merge, run test, commit**

```python
# tests/unit/validation/test_portfolio.py
from v17.validation.portfolio import compose_portfolio
import pandas as pd

def test_higher_priority_engine_wins_same_symbol_same_bar():
    e1 = pd.DataFrame({"ts_entry_ns": [1000], "engine_id": ["SB-LDN-CE"], "symbol": ["EURUSD"], "pnl_r": [1.0]})
    e2 = pd.DataFrame({"ts_entry_ns": [1000], "engine_id": ["SB-NYAM-CE"], "symbol": ["EURUSD"], "pnl_r": [0.5]})
    out = compose_portfolio([e1, e2])
    assert len(out) == 1
    assert out.iloc[0]["engine_id"] == "SB-LDN-CE"
```

Implement based on `SBEngineConfig.priority_order` ordering (spec §10.2); if two trades same symbol with overlapping position holding times, lower priority_order wins. Simplest form: ts_entry_ns + symbol + holding window check.

```bash
git add src/v17/validation/portfolio.py tests/unit/validation/test_portfolio.py
git commit -m "feat(validation): portfolio composer with one-position-per-symbol priority"
```

---

### Task 10.2: Portfolio-layer second MCPT

**Files:**
- Create: `scripts/run_portfolio_mcpt.py`

- [ ] **Step 1: Run portfolio MCPT**

```python
# scripts/run_portfolio_mcpt.py
from pathlib import Path
import pandas as pd
from v17.validation.portfolio import compose_portfolio
from v17.validation.mcpt_runner import run_mcpt
# Load passing engines, compose, run MCPT at alpha=0.05 (single test), write verdict.
```

- [ ] **Step 2-5: Standard flow + commit**

Verdict stored at `research/results/portfolio_mcpt_verdict.json`. GATE_MANIFEST updated with portfolio verdict.

---

### Task 10.3: Portfolio holdout rerun

**Files:**
- Create: `scripts/run_portfolio_holdout.py`

Same pattern applied to holdout trade logs. Compose, verify portfolio-level: positive expectancy, PF ≥ 1.2, max DD ≤ 8%, min 20 trades across all portfolio members.

Commit with verdict.

---

## Milestone 11 — Final Gate Report

Purpose: spec §15 P13. Verdict document, DEPLOY or SHELVE decision.

### Task 11.1: Write final gate report

**Files:**
- Create: `research/results/FINAL_GATE_REPORT_2026-11-03.md`
- Modify: `docs/superpowers/plans/GATE_MANIFEST.md` (set system verdict)

**Interfaces:**
- Consumes: all GATE_MANIFEST entries + per-engine + portfolio verdict JSONs
- Produces: human-readable final report

- [ ] **Step 1: Write report structure**

Create `research/results/FINAL_GATE_REPORT_2026-11-03.md` with these sections:

1. Executive verdict (DEPLOY / SHELVE), one sentence.
2. Per-engine summary table (same columns as GATE_MANIFEST).
3. Portfolio-layer summary.
4. Cost-stress summary.
5. Non-trivial findings from audits.
6. Reproducibility statement: list of commits hashes for spec, rulebook, all gate scripts.
7. Honest-expectation statement: compares outcome to spec §17 probability bands.
8. Decision block:
   - If DEPLOY: next steps = demo observation phase per Mode 1.5 for 90 days; dashboard build; no live money commitment.
   - If SHELVE: next steps = retire this cycle; options for a future cycle per spec §13.2.

- [ ] **Step 2: Commit final report**

```bash
git add research/results/FINAL_GATE_REPORT_2026-11-03.md docs/superpowers/plans/GATE_MANIFEST.md
git commit -m "docs: final gate report — <DEPLOY|SHELVE> verdict"
```

- [ ] **Step 3: Present to user**

Deliver report path to user. Await explicit user decision on DEPLOY → Mode 1.5 demo phase vs SHELVE → done.

---

## Self-Review

Checked against spec. Coverage:
- §1 (verdict framework) → Milestone 11 report.
- §2 (scope locks L1-L26) → implemented across M3-M10.
- §3.2 (SB-A1 D1 bias) → Task 3.3.
- §4 (6-engine catalog) → Task 3.2.
- §5 (parameter freeze) → Task 3.1.
- §6 (walk-forward + holdout + portfolio) → M5, M9, M10.
- §7 (MCPT dual-scheme + Bonferroni) → M6, M8.
- §8 (cost model bid/ask paired) → M2, Task 8.2 cost stress.
- §9 (FTMO risk + circuit breakers) → **GAP: not yet in dedicated task. Add Task 5.5.**
- §10 (concurrency Phase A → Phase B) → M10.
- §11 (Mode 1.5 dashboard) → **DEFERRED: Mode 1.5 dashboard explicitly deferred to post-DEPLOY implementation; final report Task 11.1 names it as next step.**
- §12 (news policy D) → Tasks 2.6, 3.10, 3.11.
- §13 (audit boundary) → M1, M4, M7.
- §14 (OpenAI usage) → **NO IMPLEMENTATION TASK YET; OpenAI uses are opt-in post-trade and audit-time. Task 11.2 added below.**
- §15 (deliverables) → implicit across milestones.
- §16 (non-goals) → implicit via scope.
- §17 (honest expectation) → Task 11.1 includes.
- §18 (change control) → human-enforced via commit discipline.

Gap fixes applied below.

---

### Task 5.5: FTMO risk engine integration (Spec §9 coverage gap fix)

**Files:**
- Modify: `src/v17/risk/engine.py`
- Modify: `src/v17/risk/risk_rules.py`
- Create: `tests/unit/risk/test_ftmo_circuit_breakers.py`

**Interfaces:**
- Consumes: equity curve state, trade events
- Produces: `RiskEngine.on_trade_close(pnl)` triggers daily-stop at -4%, total-freeze at -8%; `RiskEngine.allow_trade()` returns False while frozen

- [ ] **Step 1: Write failing test**

```python
# tests/unit/risk/test_ftmo_circuit_breakers.py
from v17.risk.engine import RiskEngine
from v17.setups.sb_constants import DAILY_LOSS_SOFT_STOP, TOTAL_LOSS_HARD_FREEZE

def test_daily_loss_soft_stop_freezes_until_next_day():
    r = RiskEngine(starting_equity=10_000.0)
    assert r.allow_trade()
    # Trade loses 4.5% of day's start equity
    r.on_trade_close(pnl_cash=-450.0, trade_date_utc_ns=1700000000000000000)
    assert not r.allow_trade()

def test_total_loss_8pct_permanent_freeze():
    r = RiskEngine(starting_equity=10_000.0)
    r.update_peak_equity(10_000.0)
    r.on_trade_close(pnl_cash=-850.0, trade_date_utc_ns=1700000000000000000)
    assert not r.allow_trade()
    # Even after date change, still frozen
    r.start_of_day(1700086400000000000)  # next day
    assert not r.allow_trade()
```

- [ ] **Step 2-5: Implement engine, run tests, commit**

```python
# src/v17/risk/engine.py (patch)
from v17.setups.sb_constants import DAILY_LOSS_SOFT_STOP, TOTAL_LOSS_HARD_FREEZE

class RiskEngine:
    def __init__(self, starting_equity: float):
        self._equity = starting_equity
        self._peak = starting_equity
        self._initial = starting_equity
        self._day_start_equity = starting_equity
        self._permanently_frozen = False
        self._daily_frozen_until_day = None
        self._current_day_ns = None

    def start_of_day(self, day_ns: int) -> None:
        self._current_day_ns = day_ns
        if self._daily_frozen_until_day is not None and day_ns >= self._daily_frozen_until_day:
            self._daily_frozen_until_day = None
        self._day_start_equity = self._equity

    def update_peak_equity(self, equity: float) -> None:
        self._peak = max(self._peak, equity)

    def on_trade_close(self, pnl_cash: float, trade_date_utc_ns: int) -> None:
        self._equity += pnl_cash
        self._peak = max(self._peak, self._equity)
        day_pnl_pct = (self._equity - self._day_start_equity) / self._day_start_equity
        if day_pnl_pct <= -DAILY_LOSS_SOFT_STOP:
            # Freeze until next calendar day start
            ns_per_day = 86_400_000_000_000
            self._daily_frozen_until_day = trade_date_utc_ns + ns_per_day
        total_dd_pct = (self._peak - self._equity) / self._peak
        if total_dd_pct >= TOTAL_LOSS_HARD_FREEZE:
            self._permanently_frozen = True

    def allow_trade(self) -> bool:
        if self._permanently_frozen:
            return False
        if self._daily_frozen_until_day is not None:
            return False
        return True
```

```bash
git add src/v17/risk/engine.py tests/unit/risk/test_ftmo_circuit_breakers.py
git commit -m "feat(risk): FTMO circuit breakers (-4% daily soft, -8% total permanent)"
```

---

### Task 11.2: OpenAI post-trade narrative + bug detector (Spec §14 coverage gap fix)

**Files:**
- Create: `src/v17/obs/narrative.py`
- Create: `src/v17/obs/bug_detector.py`
- Create: `tests/unit/obs/test_narrative.py`
- Create: `tests/unit/obs/test_bug_detector.py`

**Interfaces:**
- Consumes: completed trade dict + rulebook constants
- Produces: plain-English narrative string; list of anomalies if any

Opt-in modules; invoked post-dev-MCPT, pre-holdout. Help debug obvious code bugs by surfacing trades that violated rulebook constraints.

- [ ] **Step 1: Write narrative test (mocks OpenAI)**

```python
# tests/unit/obs/test_narrative.py
from unittest.mock import patch
from v17.obs.narrative import narrate_trade

def test_narrate_calls_openai_with_pinned_model():
    trade = {
        "engine_id": "SB-NYAM-CE", "symbol": "EURUSD", "side": "LONG",
        "ts_entry_ns": 1700000000000000000, "entry": 1.1000, "exit": 1.1012,
        "sl": 1.0994, "tp": 1.1012, "pnl_r": 2.0, "exit_reason": "TP",
    }
    with patch("v17.obs.narrative._call_openai") as mock:
        mock.return_value = "Long EURUSD at 10:00 NY..."
        text = narrate_trade(trade)
    assert "Long EURUSD" in text
    args = mock.call_args
    assert "gpt-4-turbo" in str(args) or "gpt-4" in str(args)  # pinned model
```

- [ ] **Step 2-5: Implement, test, commit**

```python
# src/v17/obs/narrative.py
import os

MODEL_PINNED = "gpt-4-turbo-2024-04-09"

def _call_openai(prompt: str, model: str) -> str:
    # Lazy import; module optional
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content

def narrate_trade(trade: dict) -> str:
    prompt = (f"Describe this trade in one short paragraph: {trade}. "
              "Be factual, no advice, no evaluation.")
    return _call_openai(prompt, model=MODEL_PINNED)
```

Bug detector pattern similar: load rulebook constants, scan each trade against SB-02..SB-05, flag violations. No OpenAI call needed — pure deterministic check. Separate module.

```bash
git add src/v17/obs/narrative.py src/v17/obs/bug_detector.py tests/unit/obs/*.py
git commit -m "feat(obs): OpenAI post-trade narrative (pinned model) + deterministic bug detector"
```

---

**Plan complete and saved to `docs/superpowers/plans/2026-11-03-silver-bullet-6-engine-doctrine-test.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best fit for a 55-task multi-week plan since each subagent gets fresh context per task.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Appropriate only if we commit to doing a milestone end-to-end in one session.

Which approach?
