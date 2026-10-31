# M11 Setup Firing Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two gates that cause zero signals in current backtests: (1) `swing_length=10` on 4h bars that confirms at most one swing per month (pinning bias BEAR or NONE forever), and (2) MSS zone-containment in the backtest precompute that checks containment at `now` rather than at CHoCH time (price has moved on by the time MSS is evaluated). After the fix, EURUSD June 2024 must produce >0 trades.

**Architecture:** Two surgical changes. (1) Lower `swing_length` from 10 to 3 in 4h swing calls in `backtest/precompute.py`, `structure/engine.py`, and `structure/bias.py` — same algorithm, different threshold. (2) Change `_mss_from_choches` in `backtest/precompute.py` to use the CHoCH candle's `price` (already available on `Swing`) instead of the current `last_1m_close` for zone-containment. The live path's `structure/mss.py` already evaluates containment at CHoCH-time close; only the backtest precompute diverges.

**Tech Stack:** No new deps. `pandas`, `pydantic`, `pytest`, `mypy`, `ruff` — all existing.

**Spec:** Addresses an unexecuted-trades defect against `docs/SPEC.md` §M2 (structure) and §M3 (setups). Not a new feature; a bug-fix that restores specified behavior ("signals must fire during killzones when ICT structure aligns").

## Global Constraints

- Python `>=3.11`, `.venv`
- `from __future__ import annotations` in every module
- `mypy --strict` + `ruff` clean on all touched files
- No new deps
- No git
- Change must be surgical: no refactor of unrelated code, no renames, no formatting churn
- Live path (`structure/engine.py`, `structure/mss.py`) must stay symmetrically correct — if backtest uses `swing_length=3` for 4h, live uses the same value
- Acceptance: `v17 backtest --symbol EURUSD --from 2024-06-01 --to 2024-06-30 --seed 42` must report `trades > 0`

---

## File Structure

```
src/v17/backtest/precompute.py       — swing_length=3 for 4h; _mss_from_choches uses s.price (Task 1 + Task 2)
src/v17/structure/engine.py          — swing_length=3 for 4h (Task 1)
src/v17/structure/bias.py            — swing_length=3 for 4h in compute_bias (Task 1)
tests/unit/structure/test_bias.py    — assert bias flips with swing_length=3 fixture (Task 1)
tests/unit/backtest/test_mss_from_choches.py — assert MSS fires when price has left zone (Task 2)
tests/integration/test_backtest_fires.py — June 2024 EURUSD smoke: trades > 0 (Task 3)
```

Do not create a new `swings.py` or `bias.py` branch. All changes are in-place parameter tweaks and one condition change.

---

## Task 1: Tune 4h swing_length from 10 to 3

**Files:**
- Modify: `src/v17/backtest/precompute.py:42` (change `swing_length=10` → `swing_length=3`)
- Modify: `src/v17/structure/engine.py:34` (change `swing_length=10` → `swing_length=3`)
- Modify: `src/v17/structure/bias.py:34` (change `swing_length=10` → `swing_length=3`)
- Create: `tests/unit/structure/test_bias.py` (bias flips with 4h swings under new threshold)

**Interfaces:**
- Consumes: `v17.structure.swings.detect_swings(df, tf, swing_length)` (already exists, no change)
- Produces: higher-cadence 4h swing stream feeding `compute_bias` / `compute_bias_fast` / backtest snapshots

- [ ] **Step 1: Write the failing test**

Create `tests/unit/structure/test_bias.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from v17.common.types import TF, Bias
from v17.structure.bias import compute_bias


def _bars_1d(closes: list[float], start: datetime) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(closes):
        ts = start + timedelta(days=i)
        rows.append({"ts": ts, "open": c, "high": c + 0.001, "low": c - 0.001, "close": c, "volume": 1, "spread_pips": 0.0})
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def _bars_4h_zigzag(start: datetime, legs: list[int]) -> pd.DataFrame:
    """Build 4h bars whose closes form clean peaks/troughs so detect_swings fires."""
    rows: list[dict[str, float | pd.Timestamp]] = []
    price = 1.1000
    ts = start
    for n_bars in legs:
        direction = 1 if (len(rows) == 0 or rows[-1]["close"] > rows[-2]["close"]) else -1
        # alternate direction each leg
        if len(rows) >= 1:
            direction = -direction
        for _ in range(n_bars):
            price += direction * 0.0005
            rows.append(
                {"ts": ts, "open": price - direction * 0.0001, "high": price + 0.0003, "low": price - 0.0003, "close": price, "volume": 1, "spread_pips": 0.0}
            )
            ts = ts + timedelta(hours=4)
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


class TestBiasAtSwingLength3:
    def test_short_history_produces_bias_not_none(self) -> None:
        # ~5 days of 1d bars rising, ~30 of 4h zigzag — swing_length=3 should fire ≥1 swing
        start = datetime(2024, 1, 1, tzinfo=UTC)
        df_1d = _bars_1d([1.10 + i * 0.001 for i in range(25)], start)
        df_4h = _bars_4h_zigzag(start, legs=[6, 6, 6, 6, 6])  # 30 bars, 5 legs
        bias = compute_bias(df_1d, df_4h)
        # With swing_length=3 and a clean zigzag of 30 bars, we must detect ≥1 swing,
        # so bias is BULL or BEAR (never NONE purely from "no 4h swing").
        assert bias != Bias.NONE
```

- [ ] **Step 2: Run test — expect FAIL**

```
python -m pytest tests/unit/structure/test_bias.py -v --tb=short
```

Expected: fails (likely NONE because `swing_length=10` detects 0 swings in 30 bars with alternating 6-bar legs).

- [ ] **Step 3: Apply the three one-line changes**

In `src/v17/backtest/precompute.py` line 42:

```python
    swings = detect_swings(bars_4h, TF.H4, swing_length=3)
```

In `src/v17/structure/engine.py` line 34:

```python
        swings_4h = detect_swings(df_4h, TF.H4, swing_length=3)
```

In `src/v17/structure/bias.py` line 34:

```python
    swings_4h = detect_swings(df_4h, TF.H4, swing_length=3)
```

Do NOT touch any other `swing_length=10` call in the codebase (sweeps, 1m CHoCHes, M15 structures all stay at 10).

- [ ] **Step 4: Run test — expect PASS**

```
python -m pytest tests/unit/structure/test_bias.py -v --tb=short
```

- [ ] **Step 5: Run neighboring tests to confirm no regression in M2/M4**

```
python -m pytest tests/unit/structure/ tests/unit/risk/ tests/unit/backtest/ -q --tb=short
```

Any failing test must be examined. If a test asserted a specific swing count that depended on `swing_length=10` on 4h, update that test's expected count to reflect the new value — do not loosen it to `>= 0`.

- [ ] **Step 6: mypy + ruff**

```
python -m mypy src/v17/backtest/precompute.py src/v17/structure/engine.py src/v17/structure/bias.py --strict
python -m ruff check src/v17/backtest/precompute.py src/v17/structure/engine.py src/v17/structure/bias.py tests/unit/structure/test_bias.py
```

Both clean.

- [ ] **Step 7: Commit** (skip — no git)

---

## Task 2: MSS zone-containment at CHoCH time (backtest path)

**Files:**
- Modify: `src/v17/backtest/precompute.py` — `_mss_from_choches` signature and body
- Modify: `src/v17/backtest/precompute.py` — `snapshot_at` call site (drops `last_1m_close` arg)
- Create: `tests/unit/backtest/test_mss_from_choches.py`

**Interfaces:**
- Consumes: `v17.common.dtos.Swing.price` (CHoCH-time price, already present on `Swing`)
- Produces: `_mss_from_choches(choches, zones, now) -> list[Swing]` — signature drops `last_close: float`

**Rationale:** The live-path `structure/mss.py` already checks zone containment at `float(closes[idx])` where `idx` is the CHoCH bar position — i.e. CHoCH-time close. The backtest's `_mss_from_choches` instead passes `last_1m_close` from `now` into containment. This diverges from live and misses every MSS where price has moved out of the zone within the 10-min window. Fix: use `float(s.price)` of the CHoCH itself.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/backtest/test_mss_from_choches.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from v17.backtest.precompute import _mss_from_choches
from v17.common.dtos import Swing, Zone
from v17.common.types import TF, Side


def _choch(at: datetime, side: Side, price: Decimal) -> Swing:
    return Swing(kind="choch", side=side, tf=TF.M1, at=at, price=price)


def _zone(created_at: datetime, side: Side, top: Decimal, bottom: Decimal) -> Zone:
    return Zone(
        symbol=None,  # type: ignore[arg-type]
        tf=TF.M15,
        kind="fvg",
        side=side,
        top=top,
        bottom=bottom,
        created_at=created_at,
        mitigated_at=None,
    )


class TestMSSFromChochesContainmentAtChochTime:
    def test_fires_when_price_was_in_zone_at_choch_time(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        choch_at = now - timedelta(minutes=3)
        # CHoCH at price 1.1050 (inside the zone); zone side matches
        choch_price = Decimal("1.1050")
        zone = _zone(choch_at - timedelta(minutes=30), Side.BUY, Decimal("1.1060"), Decimal("1.1040"))
        choches = [_choch(choch_at, Side.BUY, choch_price)]
        # last_close at `now` has drifted OUT of the zone — old code would skip
        result = _mss_from_choches(choches, [zone], now)
        assert len(result) == 1
        assert result[0].kind == "mss"
        assert result[0].side == Side.BUY

    def test_skips_when_price_was_not_in_zone_at_choch_time(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        choch_at = now - timedelta(minutes=3)
        # CHoCH price 1.1100 is above zone 1.1040-1.1060 — not contained at CHoCH time
        choch_price = Decimal("1.1100")
        zone = _zone(choch_at - timedelta(minutes=30), Side.BUY, Decimal("1.1060"), Decimal("1.1040"))
        choches = [_choch(choch_at, Side.BUY, choch_price)]
        result = _mss_from_choches(choches, [zone], now)
        assert result == []

    def test_window_still_enforced(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        choch_at = now - timedelta(minutes=11)  # outside 10-min window
        zone = _zone(choch_at - timedelta(minutes=30), Side.BUY, Decimal("1.1060"), Decimal("1.1040"))
        choches = [_choch(choch_at, Side.BUY, Decimal("1.1050"))]
        result = _mss_from_choches(choches, [zone], now)
        assert result == []

    def test_mitigated_zone_rejected(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        choch_at = now - timedelta(minutes=3)
        zone = Zone(
            symbol=None,  # type: ignore[arg-type]
            tf=TF.M15,
            kind="fvg",
            side=Side.BUY,
            top=Decimal("1.1060"),
            bottom=Decimal("1.1040"),
            created_at=choch_at - timedelta(minutes=30),
            mitigated_at=choch_at - timedelta(minutes=5),
        )
        choches = [_choch(choch_at, Side.BUY, Decimal("1.1050"))]
        result = _mss_from_choches(choches, [zone], now)
        assert result == []

    def test_side_mismatch_rejected(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        choch_at = now - timedelta(minutes=3)
        zone = _zone(choch_at - timedelta(minutes=30), Side.SELL, Decimal("1.1060"), Decimal("1.1040"))
        choches = [_choch(choch_at, Side.BUY, Decimal("1.1050"))]
        result = _mss_from_choches(choches, [zone], now)
        assert result == []
```

- [ ] **Step 2: Run test — expect FAIL on `test_fires_when_price_was_in_zone_at_choch_time`**

```
python -m pytest tests/unit/backtest/test_mss_from_choches.py -v --tb=short
```

The first test will fail because old `_mss_from_choches` requires `last_close` arg and uses it for containment. Collection may error on signature mismatch — that is the expected FAIL.

- [ ] **Step 3: Change `_mss_from_choches` in `src/v17/backtest/precompute.py`**

Replace the function (currently at lines 78–94) with:

```python
def _mss_from_choches(
    choches: list[Swing], zones: list[Zone], now: datetime
) -> list[Swing]:
    window_start = now - timedelta(minutes=_MSS_WINDOW_MIN)
    out: list[Swing] = []
    for s in choches:
        if s.at > now or s.at < window_start:
            continue
        choch_price = float(s.price)
        for z in zones:
            if z.mitigated_at is not None:
                continue
            if z.side != s.side:
                continue
            if float(z.bottom) <= choch_price <= float(z.top):
                out.append(Swing(kind="mss", side=s.side, tf=s.tf, at=s.at, price=s.price))
                break
    return out
```

- [ ] **Step 4: Update the call site in `snapshot_at`**

In `src/v17/backtest/precompute.py` the current body around line 117–119 reads:

```python
    bars_1m_sub = pre.bars_1m[pre.bars_1m["ts"] <= pd.Timestamp(now)]
    last_1m_close = float(bars_1m_sub["close"].iloc[-1]) if not bars_1m_sub.empty else 0.0
    mss = _mss_from_choches(pre.choches_1m, zones_active, now, last_1m_close)
```

Change to:

```python
    mss = _mss_from_choches(pre.choches_1m, zones_active, now)
```

Delete the now-dead `bars_1m_sub` and `last_1m_close` lines. (They are only used by the MSS call.)

- [ ] **Step 5: Run tests — expect PASS**

```
python -m pytest tests/unit/backtest/test_mss_from_choches.py -v --tb=short
```

- [ ] **Step 6: Neighboring tests**

```
python -m pytest tests/unit/backtest/ -q --tb=short
```

If any pre-existing test invoked `_mss_from_choches` with the four-arg signature, update it to the three-arg form.

- [ ] **Step 7: mypy + ruff**

```
python -m mypy src/v17/backtest/precompute.py --strict
python -m ruff check src/v17/backtest/precompute.py tests/unit/backtest/test_mss_from_choches.py
```

Both clean.

- [ ] **Step 8: Commit** (skip — no git)

---

## Task 3: Backtest fires + metrics report + full suite

**Files:**
- Create: `tests/integration/test_backtest_fires.py`

**Interfaces:**
- Consumes: Tasks 1 + 2 fixes end-to-end via `v17.backtest.cli.backtest`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_backtest_fires.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from v17.cli import app


@pytest.mark.skipif(
    not Path("data/parquet/EURUSD/1m/year=2024").exists(),
    reason="requires EURUSD 2024 parquet bars (run `v17 ingest` first)",
)
class TestBacktestFiresAfterM11:
    def test_june_2024_eurusd_produces_trades(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "backtest",
                "--symbol",
                "EURUSD",
                "--from",
                "2024-06-01",
                "--to",
                "2024-06-30",
                "--seed",
                "42",
            ],
        )
        assert result.exit_code == 0, result.output
        # Extract run_id and inspect metrics.json
        token = next(t for t in result.output.split() if t.startswith("run_id="))
        run_id = token.split("=", 1)[1]
        metrics_path = Path("runs") / run_id / "metrics.json"
        assert metrics_path.exists()
        metrics = json.loads(metrics_path.read_text())
        assert metrics["trades"] > 0, f"expected trades>0 after M11 fix, got {metrics}"
```

The `skipif` keeps the test green on CI machines without the data; where data exists, trades must fire.

- [ ] **Step 2: Run the full suite**

```
python -m pytest tests/ -q --tb=short
```

All must pass (including existing 302). The integration test either runs and passes with `trades > 0`, or is skipped if parquet data is absent.

- [ ] **Step 3: Run the actual backtest and capture metrics**

```
python -m v17.cli backtest --symbol EURUSD --from 2024-06-01 --to 2024-06-30 --seed 42
```

Record output in the task report. Expected: `trades > 0`. Metrics (winrate / PF / DD / Sharpe) are whatever they are — this task does not optimize them, it unblocks measurement.

- [ ] **Step 4: Final mypy + ruff on M11 touched files**

```
python -m mypy src/v17/backtest/precompute.py src/v17/structure/engine.py src/v17/structure/bias.py --strict
python -m ruff check src/v17/backtest/precompute.py src/v17/structure/engine.py src/v17/structure/bias.py tests/unit/structure/test_bias.py tests/unit/backtest/test_mss_from_choches.py tests/integration/test_backtest_fires.py
```

Both clean on all touched files.

- [ ] **Step 5: Commit** (skip — no git)

---

## Self-Review

**Spec coverage:**
- [x] `swing_length=3` tuning for 4h bias — applied in both backtest precompute and live structure engine, symmetrically, so backtest and live see the same bias cadence
- [x] MSS zone-containment at CHoCH time — fixes backtest-vs-live divergence; live path (`structure/mss.py:42`) already uses `float(closes[idx])` which is CHoCH-time close
- [x] Regression test for bias flip at new `swing_length`
- [x] Regression tests for MSS containment semantics (fires, skips, window, mitigated, side-mismatch)
- [x] Acceptance: June 2024 EURUSD must produce `trades > 0`

**Type consistency check:**
- `_mss_from_choches` signature drops 4th arg `last_close: float`; the single call site in `snapshot_at` is updated in Task 2 Step 4
- All three edits in Task 1 are literal integer swaps — no type contract change

**Placeholder scan:** None.

**Risk register:**
- `swing_length=3` on 4h may produce more false bias flips on noisy months. Mitigation: Task 3 does not optimize metrics; validation gate (M6) is the long-term quality filter. If June 2024 PF stays < 1.3, that is a legitimate validation-gate rejection, not a reason to roll back M11.
- MSS fix is a semantic correction (backtest ↔ live parity), not a loosening. No new false positives expected.
- Zero changes to M4 (risk), M5 (backtest harness), M7–M10. Blast radius: structure + precompute only.
