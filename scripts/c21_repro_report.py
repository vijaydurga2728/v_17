"""Cycle 21 reproducibility report: code version, environment, config fingerprints, data hashes, test result.

Runs NO strategy logic. Writes out/c21/repro_report.md.
"""

from __future__ import annotations

import dataclasses
import hashlib
import platform
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.smc_sb.config import (  # noqa: E402
    BASELINE,
    CONFIG_VERSION,
    EXPERIMENT_OTE,
    EXPERIMENT_SMT,
    INSTRUMENTS,
    SMT_PARTNER,
)
from v17.smc_sb.data import source_files  # noqa: E402

OUT = REPO / "out" / "c21"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit/smc_sb", "-q", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,  # a failing test run must still be reported, not hidden
    )
    summary = tests.stdout.strip().splitlines()[-1] if tests.stdout.strip() else tests.stderr[-300:]
    lines = [
        "# Cycle 21 reproducibility report",
        "",
        f"- Git HEAD: `{git('rev-parse', 'HEAD')}` on branch `{git('branch', '--show-current')}`",
        f"- Uncommitted changes in cycle 21 paths: `{git('status', '--short', 'src/v17/smc_sb', 'tests/unit/smc_sb', 'scripts/c21_data_audit.py', 'scripts/c21_repro_report.py') or 'none'}`",
        f"- Spec: `docs/superpowers/specs/2026-11-18-cycle21-sb-smc-spec-v1.md` (frozen in commit `{git('log', '--format=%h', '-1', '--', 'docs/superpowers/specs/2026-11-18-cycle21-sb-smc-spec-v1.md')}`)",
        f"- Python {platform.python_version()} ({platform.system()} {platform.release()})",
        "- Packages: "
        + ", ".join(
            f"{p} {version(p)}" for p in ("numpy", "pandas", "pyarrow", "pandas_market_calendars")
        ),
        f"- Tests: `python -m pytest tests/unit/smc_sb -q` -> **{summary}** (exit {tests.returncode})",
        "- Determinism: no randomness in signal/execution code; the luck test uses `numpy.random.default_rng(seed)` "
        "with a fixed per-instrument seed (to be set in the execution pre-registration).",
        "",
        f"## Configuration (CONFIG_VERSION {CONFIG_VERSION})",
        "",
        "| variant | fingerprint | entry_model | smt_enabled |",
        "|---|---|---|---|",
    ]
    for name, c in (
        ("BASELINE", BASELINE),
        ("EXPERIMENT_OTE", EXPERIMENT_OTE),
        ("EXPERIMENT_SMT", EXPERIMENT_SMT),
    ):
        lines.append(f"| {name} | `{c.fingerprint()}` | {c.entry_model} | {c.smt_enabled} |")
    lines += ["", "All parameters (baseline):", "", "```"]
    lines += [f"{k} = {v!r}" for k, v in dataclasses.asdict(BASELINE).items()]
    lines += [
        "```",
        "",
        f"Instruments: `{INSTRUMENTS}`  SMT partners (experiment only): `{SMT_PARTNER}`",
        "",
    ]
    lines += ["## Data files (SHA-256)", ""]
    for name in INSTRUMENTS:
        files = source_files(name)
        combo = hashlib.sha256()
        rows = []
        for f in files:
            h = sha256(f)
            combo.update(h.encode())
            rows.append(f"  - `{f.relative_to(REPO).as_posix()}` `{h[:16]}`")
        lines.append(f"- **{name}**: {len(files)} files, combined hash `{combo.hexdigest()[:16]}`")
        lines += rows
    lines += [
        "",
        "## Reproduce",
        "",
        "```",
        "python -m pytest tests/unit/smc_sb -q",
        "python scripts/c21_data_audit.py      # writes out/c21/data_audit.{md,json}",
        "python scripts/c21_repro_report.py    # writes this file",
        "```",
        "",
        "No strategy run exists yet (execution gate in spec §0).",
    ]
    (OUT / "repro_report.md").write_text("\n".join(lines) + "\n", "utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
