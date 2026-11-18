"""Cycle 21 Silver Bullet SMC — versioned configuration.

Every value here maps to the frozen spec `docs/superpowers/specs/2026-11-18-cycle21-sb-smc-spec-v1.md`
(user decisions D1-D16, interpretations R1-R30, review 1 applied). Changing any value requires a new CONFIG_VERSION and
must happen before strategy execution, never after inspecting results.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace

CONFIG_VERSION = "21.2.0"

# Spec name -> Dukascopy M1 bid/ask symbol (spec §2).
INSTRUMENTS: dict[str, str] = {
    "NAS100": "USATECHIDXUSD",
    "SPX": "USA500IDXUSD",
    "US30": "USA30IDXUSD",
}
# D11 / R25: SMT partner mapping, explicitly configured (experiment only).
SMT_PARTNER: dict[str, str] = {"NAS100": "SPX", "SPX": "NAS100", "US30": "SPX"}


@dataclass(frozen=True)
class StrategyConfig:
    entry_model: str = "A"  # "A" = FVG-only baseline, "B" = FVG + OTE (separate experiment)
    smt_enabled: bool = False  # D11: disabled in baseline
    daily_rollover_hour: int = 17  # R1
    window_start: str = "10:00"  # spec §2
    window_end: str = "11:00"
    order_expiry: str = "11:05"  # D8 (exclusive)
    force_close: str = "16:00"  # D10 / R16
    asia_start_hour: int = 20  # D2: 20:00-00:00 NY, assigned to following trading date
    sweep_refs: tuple[str, ...] = ("PD", "ASIA")  # D2
    daily_pivot_left: int = 2  # D1
    daily_pivot_right: int = 2
    mss_pivot_left: int = 2  # D3
    mss_pivot_right: int = 2
    fvg_tf_min: int = 5  # D4
    mss_tf_min: int = 15  # D4
    ote_low: float = 0.62  # D7 (Model B only)
    ote_high: float = 0.79
    min_rr: float = 2.0  # D13 / R17
    slippage_pts: float = 0.5  # D16
    commission_pts: float = 0.0  # D16 / R22 (pending MT5 spec verification)
    cost_multiplier: float = 1.0  # R23: 2.0 = doubled spread + slippage sensitivity
    data_check_start: str = "09:30"  # R20
    null_perms: int = 5000  # R24 / 3a
    null_max_attempts: int = 100  # 3a: redraws per unfilled control trade
    null_seed_base: int = 2026112100  # 3a: + 10 * instrument_index + variant_index

    def __post_init__(self) -> None:
        if self.entry_model not in ("A", "B"):
            raise ValueError(f"entry_model must be 'A' or 'B', got {self.entry_model!r}")
        if not set(self.sweep_refs) <= {"PD", "ASIA"}:
            raise ValueError(f"unknown sweep reference in {self.sweep_refs!r}")
        if not 0.0 < self.ote_low < self.ote_high < 1.0:
            raise ValueError("OTE bounds must satisfy 0 < low < high < 1")
        if self.cost_multiplier < 1.0:
            raise ValueError("cost_multiplier < 1 would understate costs")

    @property
    def version(self) -> str:
        return CONFIG_VERSION

    def fingerprint(self) -> str:
        """Stable hash of every parameter + version (recorded with every run)."""
        blob = json.dumps({"version": CONFIG_VERSION, **asdict(self)}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    @property
    def slippage(self) -> float:
        return self.slippage_pts * self.cost_multiplier


BASELINE = StrategyConfig()
EXPERIMENT_OTE = replace(BASELINE, entry_model="B")
EXPERIMENT_SMT = replace(BASELINE, smt_enabled=True)
INSTRUMENT_INDEX: dict[str, int] = {"NAS100": 0, "SPX": 1, "US30": 2}
ALPHA_PER_INSTRUMENT = 0.05 / 3  # R26 / 3a Bonferroni over 3 instruments


def variant_index(cfg: StrategyConfig) -> int:
    """3a seed component: A 0, B 1, SMT 2."""
    return 2 if cfg.smt_enabled else (1 if cfg.entry_model == "B" else 0)
