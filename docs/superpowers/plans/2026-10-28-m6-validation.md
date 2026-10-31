# M6 Validation Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Produce the hard gate that stands between a backtest `RunReport` and any live/demo trading. If every §6.2 threshold is met, write `data/state/GATE_PASSED` with the full report; otherwise revoke the sentinel (if present) and exit non-zero. The live runner (M8) reads this file at pre-flight and refuses to arm without it.

**Architecture:** Pure `evaluate(report) -> (passed, reasons)` that returns a bool + a list of threshold failures. A thin `GateWriter` wraps the two filesystem effects (write/revoke). CLI `v17 validate --run <id>` loads the run artifacts, calls the evaluator, writes/revokes the sentinel, and exits 0/1.

**Tech Stack:** Python 3.11+, pydantic, pyarrow (reads M5 artifacts), typer.

**Spec:** `docs/SPEC.md` §6.2 (thresholds), §7 M6, §6.9 Boundaries ("Never bypass the validation gate"); `docs/API.md` §5 M6.

## Global Constraints

- Python `>=3.11`, `.venv`.
- UTC canonical.
- `pydantic.BaseModel` frozen DTOs.
- `mypy --strict` + `ruff` clean on `src/v17/validation/`.
- Coverage ≥ 90% on `src/v17/validation/` (pure logic + thin FS).
- No I/O inside `evaluate()`; FS calls only in `GateWriter`.
- Sentinel path: `<data_root>/state/GATE_PASSED` (JSON content = passed `RunReport` + ISO timestamp + checksum).
- Thresholds live in exactly one file: `src/v17/validation/thresholds.py` (SPEC §6.2 verbatim).
- No git.

## File Structure

```
src/v17/validation/__init__.py                                       Task 1
src/v17/validation/ports.py                 # ValidationGate Protocol    Task 1
src/v17/validation/thresholds.py            # SPEC §6.2 constants         Task 1
src/v17/validation/evaluate.py              # pure evaluate()             Task 2
src/v17/validation/gate.py                  # GateWriter + load helpers   Task 3
src/v17/validation/cli.py                   # `v17 validate` subcommand   Task 4

tests/unit/validation/test_thresholds.py                                  Task 1
tests/unit/validation/test_evaluate.py                                    Task 2
tests/unit/validation/test_gate.py                                        Task 3
tests/integration/test_validate_cli.py                                    Task 4-5
```

---

## Task 1: Thresholds + Protocol

**Files:**
- Create: `src/v17/validation/__init__.py`, `src/v17/validation/ports.py`, `src/v17/validation/thresholds.py`
- Test: `tests/unit/validation/test_thresholds.py`

**Interfaces:**
- `VALIDATION_THRESHOLDS: dict[str, float]` keys: `min_pf`, `min_sharpe`, `max_dd_pct`, `min_winrate`, `min_mc_p5_pf`, `max_mc_p95_dd_pct`, `min_oos_trades`, `min_folds_passed`. Values match SPEC §6.2.
- `ValidationGate` Protocol per `docs/API.md` §5 M6.

- [ ] **Step 1: Write failing test** verifying each threshold key exists + locked value.

```python
# tests/unit/validation/test_thresholds.py
from v17.validation.thresholds import VALIDATION_THRESHOLDS

def test_locked_values() -> None:
    t = VALIDATION_THRESHOLDS
    assert t["min_pf"] == 1.8
    assert t["min_sharpe"] == 2.0
    assert t["max_dd_pct"] == 6.0
    assert t["min_winrate"] == 0.50
    assert t["min_mc_p5_pf"] == 1.3
    assert t["max_mc_p95_dd_pct"] == 8.0
    assert t["min_oos_trades"] == 200
    assert t["min_folds_passed"] == 4
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/v17/validation/thresholds.py
from __future__ import annotations
from typing import Final


VALIDATION_THRESHOLDS: Final[dict[str, float]] = {
    "min_pf": 1.8,
    "min_sharpe": 2.0,
    "max_dd_pct": 6.0,
    "min_winrate": 0.50,
    "min_mc_p5_pf": 1.3,
    "max_mc_p95_dd_pct": 8.0,
    "min_oos_trades": 200,
    "min_folds_passed": 4,
}
```

```python
# src/v17/validation/ports.py
from __future__ import annotations
from typing import Protocol
from v17.common.dtos import RunReport


class ValidationGate(Protocol):
    def evaluate(self, report: RunReport) -> tuple[bool, list[str]]: ...
    def write_sentinel(self, report: RunReport) -> None: ...
    def revoke(self) -> None: ...
```

- [ ] **Step 4: PASS**

---

## Task 2: `evaluate()` pure function

**Files:**
- Create: `src/v17/validation/evaluate.py`
- Test: `tests/unit/validation/test_evaluate.py`

**Interfaces:**
- `evaluate(report: RunReport, thresholds: dict[str, float] = VALIDATION_THRESHOLDS) -> tuple[bool, list[str]]`.
  Returns `(True, [])` iff every threshold is met. Otherwise `(False, reasons)` where each reason is a short human-readable string naming the metric and the gap, e.g. `"pf 1.60 < 1.80"`.

- [ ] **Step 1: Write failing tests** covering: all-pass, each individual fail path, multi-fail.

```python
# tests/unit/validation/test_evaluate.py
from datetime import UTC, datetime
from decimal import Decimal
from v17.common.dtos import BacktestConfig, RunReport
from v17.common.types import RunId, Symbol
from v17.validation.evaluate import evaluate


def _report(**over: object) -> RunReport:
    base = dict(
        run_id=RunId("x"),
        config=BacktestConfig(
            symbol=Symbol("EURUSD"),
            start=datetime(2015, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        trades=500, winrate=0.55, pf=1.9, sharpe=2.1, max_dd_pct=5.0,
        net_pnl=Decimal("12000"), oos_trades=250, oos_pf=1.85,
        oos_sharpe=2.0, oos_max_dd_pct=5.5,
        walkforward_folds_passed=6, mc_p5_pf=1.4, mc_p95_max_dd_pct=7.0,
    )
    base.update(over)
    return RunReport(**base)  # type: ignore[arg-type]


def test_all_pass() -> None:
    ok, reasons = evaluate(_report())
    assert ok is True and reasons == []

def test_fail_pf() -> None:
    ok, reasons = evaluate(_report(pf=1.6, oos_pf=1.6))
    assert ok is False and any("pf" in r for r in reasons)

def test_fail_sharpe_and_winrate() -> None:
    ok, reasons = evaluate(_report(sharpe=1.0, oos_sharpe=1.0, winrate=0.40))
    assert ok is False and len(reasons) >= 2

def test_fail_max_dd() -> None:
    ok, reasons = evaluate(_report(max_dd_pct=7.0, oos_max_dd_pct=7.0))
    assert ok is False and any("dd" in r for r in reasons)

def test_fail_mc_fail_folds_fail_oos_count() -> None:
    ok, reasons = evaluate(_report(mc_p5_pf=1.1, mc_p95_max_dd_pct=9.0,
                                   walkforward_folds_passed=2, oos_trades=100))
    assert ok is False
    assert any("mc_p5_pf" in r for r in reasons)
    assert any("mc_p95" in r for r in reasons)
    assert any("folds" in r for r in reasons)
    assert any("oos_trades" in r for r in reasons)
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/v17/validation/evaluate.py
from __future__ import annotations
from v17.common.dtos import RunReport
from v17.validation.thresholds import VALIDATION_THRESHOLDS


def evaluate(
    report: RunReport,
    thresholds: dict[str, float] = VALIDATION_THRESHOLDS,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    # Full-run baseline metrics must also hold
    if report.pf < thresholds["min_pf"]:
        reasons.append(f"pf {report.pf:.2f} < {thresholds['min_pf']}")
    if report.sharpe < thresholds["min_sharpe"]:
        reasons.append(f"sharpe {report.sharpe:.2f} < {thresholds['min_sharpe']}")
    if report.max_dd_pct >= thresholds["max_dd_pct"]:
        reasons.append(f"max_dd {report.max_dd_pct:.2f}% >= {thresholds['max_dd_pct']}%")
    if report.winrate < thresholds["min_winrate"]:
        reasons.append(f"winrate {report.winrate:.2f} < {thresholds['min_winrate']}")
    # OOS metrics are the real gate
    if report.oos_pf < thresholds["min_pf"]:
        reasons.append(f"oos_pf {report.oos_pf:.2f} < {thresholds['min_pf']}")
    if report.oos_sharpe < thresholds["min_sharpe"]:
        reasons.append(f"oos_sharpe {report.oos_sharpe:.2f} < {thresholds['min_sharpe']}")
    if report.oos_max_dd_pct >= thresholds["max_dd_pct"]:
        reasons.append(f"oos_max_dd {report.oos_max_dd_pct:.2f}% >= {thresholds['max_dd_pct']}%")
    if report.oos_trades < thresholds["min_oos_trades"]:
        reasons.append(f"oos_trades {report.oos_trades} < {int(thresholds['min_oos_trades'])}")
    # Monte Carlo tail
    if report.mc_p5_pf < thresholds["min_mc_p5_pf"]:
        reasons.append(f"mc_p5_pf {report.mc_p5_pf:.2f} < {thresholds['min_mc_p5_pf']}")
    if report.mc_p95_max_dd_pct > thresholds["max_mc_p95_dd_pct"]:
        reasons.append(
            f"mc_p95_max_dd {report.mc_p95_max_dd_pct:.2f}% > {thresholds['max_mc_p95_dd_pct']}%"
        )
    # Walk-forward diversity
    if report.walkforward_folds_passed < thresholds["min_folds_passed"]:
        reasons.append(
            f"folds_passed {report.walkforward_folds_passed} < {int(thresholds['min_folds_passed'])}"
        )
    return (len(reasons) == 0, reasons)
```

- [ ] **Step 4: PASS**

---

## Task 3: GateWriter — sentinel I/O

**Files:**
- Create: `src/v17/validation/gate.py`
- Test: `tests/unit/validation/test_gate.py`

**Interfaces:**
- `GateWriter(state_root: Path)` with methods `write_sentinel(report: RunReport, now: datetime | None = None) -> Path`, `revoke() -> bool` (True if deleted), `is_active() -> bool`, `read_active() -> dict | None`.
- Sentinel file: `<state_root>/GATE_PASSED` (JSON). Content: `{"run_id": ..., "written_at": ISO, "report": <report.model_dump>}`.
- Idempotent: writing overwrites, revoking non-existent returns False.

- [ ] **Step 1: Write failing test** covering write + read-active + revoke lifecycle.

```python
# tests/unit/validation/test_gate.py
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from v17.common.dtos import BacktestConfig, RunReport
from v17.common.types import RunId, Symbol
from v17.validation.gate import GateWriter


def _report() -> RunReport:
    cfg = BacktestConfig(
        symbol=Symbol("EURUSD"),
        start=datetime(2015, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return RunReport(run_id=RunId("abc"), config=cfg, trades=250, winrate=0.55,
                     pf=1.9, sharpe=2.1, max_dd_pct=5.0, net_pnl=Decimal("12000"),
                     oos_trades=250, oos_pf=1.85, oos_sharpe=2.0, oos_max_dd_pct=5.5,
                     walkforward_folds_passed=6, mc_p5_pf=1.4, mc_p95_max_dd_pct=7.0)


def test_write_then_active(tmp_path: Path) -> None:
    g = GateWriter(tmp_path)
    assert g.is_active() is False
    g.write_sentinel(_report(), now=datetime(2026, 10, 28, tzinfo=UTC))
    assert g.is_active() is True
    active = g.read_active()
    assert active is not None
    assert active["run_id"] == "abc"


def test_revoke(tmp_path: Path) -> None:
    g = GateWriter(tmp_path)
    g.write_sentinel(_report())
    assert g.revoke() is True
    assert g.is_active() is False
    assert g.revoke() is False
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/v17/validation/gate.py
from __future__ import annotations
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from v17.common.dtos import RunReport


class GateWriter:
    SENTINEL = "GATE_PASSED"

    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root

    @property
    def _path(self) -> Path:
        return self.state_root / self.SENTINEL

    def write_sentinel(self, report: RunReport, now: datetime | None = None) -> Path:
        self.state_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": str(report.run_id),
            "written_at": (now or datetime.now(UTC)).isoformat(),
            "report": report.model_dump(mode="json"),
        }
        self._path.write_text(json.dumps(payload, default=_json_default, indent=2))
        return self._path

    def revoke(self) -> bool:
        if self._path.exists():
            self._path.unlink()
            return True
        return False

    def is_active(self) -> bool:
        return self._path.exists()

    def read_active(self) -> dict[str, Any] | None:
        if not self.is_active():
            return None
        return json.loads(self._path.read_text())


def _json_default(x: object) -> object:
    if isinstance(x, Decimal):
        return float(x)
    iso = getattr(x, "isoformat", None)
    if callable(iso):
        return iso()
    raise TypeError(f"not serializable: {type(x)}")
```

- [ ] **Step 4: PASS**

---

## Task 4: `v17 validate` CLI

**Files:**
- Create: `src/v17/validation/cli.py`
- Modify: `src/v17/cli.py` (register `validate`)
- Test: integration test in Task 5.

**Interfaces:**
- `v17 validate --run <run_id>` → loads `runs/<run_id>/metrics.json`, re-materialises a `RunReport` (also pulls `montecarlo.json`, `walkforward.json`), runs `evaluate()`. If pass → `write_sentinel`; else → `revoke` (safety) and print each reason. Exit 0 on pass, 1 on fail.

- [ ] **Step 1: Implement**

```python
# src/v17/validation/cli.py
from __future__ import annotations
import json
from decimal import Decimal
from pathlib import Path
import typer
from v17.common.dtos import BacktestConfig, RunReport
from v17.common.types import RunId, Symbol
from v17.config import get_settings
from v17.validation.evaluate import evaluate
from v17.validation.gate import GateWriter


def validate(run: str = typer.Option(..., "--run")) -> None:
    s = get_settings()
    run_dir = s.project_root / "runs" / run
    if not run_dir.exists():
        raise typer.BadParameter(f"no run dir {run_dir}")
    metrics = json.loads((run_dir / "metrics.json").read_text())
    mc = {}
    mc_path = run_dir / "montecarlo.json"
    if mc_path.exists():
        mc = json.loads(mc_path.read_text())
    wf = {}
    wf_path = run_dir / "walkforward.json"
    if wf_path.exists():
        wf = json.loads(wf_path.read_text())

    # we only have config materialised if a config.toml exists; otherwise reconstruct minimum
    cfg = BacktestConfig(
        symbol=Symbol("EURUSD"),
        start=__import__("datetime").datetime(2015, 1, 1,
            tzinfo=__import__("datetime").UTC),
        end=__import__("datetime").datetime(2026, 1, 1,
            tzinfo=__import__("datetime").UTC),
    )
    report = RunReport(
        run_id=RunId(run),
        config=cfg,
        trades=int(metrics.get("trades", 0)),
        winrate=float(metrics.get("winrate", 0.0)),
        pf=float(metrics.get("pf", 0.0)),
        sharpe=float(metrics.get("sharpe", 0.0)),
        max_dd_pct=float(metrics.get("max_dd_pct", 0.0)),
        net_pnl=Decimal(str(metrics.get("net_pnl", 0))),
        oos_trades=int(metrics.get("oos_trades", metrics.get("trades", 0))),
        oos_pf=float(metrics.get("oos_pf", metrics.get("pf", 0.0))),
        oos_sharpe=float(metrics.get("oos_sharpe", metrics.get("sharpe", 0.0))),
        oos_max_dd_pct=float(metrics.get("oos_max_dd_pct", metrics.get("max_dd_pct", 0.0))),
        walkforward_folds_passed=int(wf.get("folds_passed", 0)),
        mc_p5_pf=float(mc.get("p5_pf", 0.0)),
        mc_p95_max_dd_pct=float(mc.get("p95_max_dd_pct", 0.0)),
    )
    ok, reasons = evaluate(report)
    gate = GateWriter(s.state_root)
    if ok:
        p = gate.write_sentinel(report)
        typer.echo(f"GATE PASSED → {p}")
        raise typer.Exit(0)
    gate.revoke()
    typer.echo("GATE FAILED. Reasons:")
    for r in reasons:
        typer.echo(f"  - {r}")
    raise typer.Exit(1)
```

- [ ] **Step 2: Wire into `src/v17/cli.py`**

```python
from v17.validation.cli import validate
app.command("validate")(validate)
```

- [ ] **Step 3: PASS lint + mypy.**

---

## Task 5: Integration test

**Files:**
- Create: `tests/integration/test_validate_cli.py`

**Interfaces:** None.

- [ ] **Step 1: Write test** that:
  1. Builds a fake `runs/<id>/` dir in `tmp_path` with `metrics.json`, `montecarlo.json`, `walkforward.json`.
  2. Points `V17_PROJECT_ROOT` at `tmp_path`.
  3. Runs `v17 validate --run <id>` with a passing payload → exits 0 → `data/state/GATE_PASSED` present.
  4. Replaces payload with a failing one → exits 1 → sentinel removed → stdout contains "GATE FAILED".

- [ ] **Step 2: Implement + run.** PASS.

---

## Self-review

- Spec §6.2 thresholds locked in `thresholds.py`.
- `evaluate()` purely functional, no I/O.
- Sentinel path matches SPEC §6.1 ("GATE_PASSED sentinel file"), SPEC §9 (`data/state/`).
- Boundary §6.9 respected: never bypass. The gate is the only producer of the sentinel.

## Done definition

- All 5 tasks pass.
- `ruff` + `mypy` clean.
- Coverage ≥ 90% on `src/v17/validation/`.
- Integration test proves write-then-revoke lifecycle via CLI.
