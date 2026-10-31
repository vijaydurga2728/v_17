# M2 Market Structure Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Produce a `StructureEngine` that takes multi-TF OHLC bars (Daily, 4H, 15m, 1m) and returns a `StructureSnapshot` containing HTF bias, detected FVG + OB zones, swings (BOS/CHoCH + MSS), and liquidity sweeps (BSL/SSL). Deterministic, pure, test-covered.

**Architecture:** Thin wrapper over `smartmoneyconcepts` (joshyattridge, MIT, ADR-0005) for FVG/BOS/CHoCH/OB/liquidity/swing primitives, plus our own ATR + MSS + bias logic to match the glossary definitions exactly. Public surface is `StructureEngine.analyze(bars_by_tf) -> StructureSnapshot`. Internals split into focused files.

**Tech Stack:** Python 3.11+, pandas 2+, numpy, `smartmoneyconcepts>=0.0.26`, hypothesis, pytest.

**Spec:** `docs/SPEC.md` §5 Domain Glossary, §7 M2; `docs/API.md` §2, §5 M2; `docs/decisions/0005-smartmoneyconcepts-dep.md`.

## Global Constraints

- Python `>=3.11`. Virtualenv `./.venv`.
- UTC canonical. All timestamps `datetime` with `tzinfo=UTC`. Naive banned.
- All detectors are **pure functions** of their inputs. No I/O.
- DTOs are frozen `pydantic.BaseModel` (`model_config = frozen=True, extra="forbid"`).
- `mypy --strict` clean on `src/v17/structure/`.
- `ruff check` clean.
- Coverage ≥ 85% on `src/v17/structure/`.
- No git, no commits.
- Package manager: `.venv/Scripts/pip`.
- Timeframes used: Daily, H4, M15, M1.
- ATR period: 14 (Wilder).
- Swing window: 10 bars (per glossary).
- OB displacement: body of next candle ≥ 2.0×ATR(14) on the OB's TF.
- MSS body threshold: 1m body > 1.5×ATR(14, 1m).
- Zone staleness: unmitigated AND age ≤ 30 bars on its TF.
- Liquidity sweep: wick beyond level AND close back inside range on the TF being evaluated.

## File Structure

```
src/v17/common/dtos.py                 # extended with Zone, Swing, Sweep, StructureSnapshot    Task 1
src/v17/structure/__init__.py                                                                   Task 1
src/v17/structure/ports.py             # StructureEngine Protocol                               Task 1
src/v17/structure/atr.py               # Wilder ATR, pure numpy/pandas                          Task 2
src/v17/structure/smc_adapter.py       # thin wrapper over smartmoneyconcepts                   Task 3
src/v17/structure/swings.py            # swing_highs_lows + BOS/CHoCH extraction                Task 4
src/v17/structure/fvg.py               # FVG detector per glossary                              Task 5
src/v17/structure/ob.py                # OB detector with 2.0×ATR displacement                  Task 6
src/v17/structure/liquidity.py         # BSL/SSL + sweep detector                               Task 7
src/v17/structure/mss.py               # 1m MSS detector                                        Task 8
src/v17/structure/bias.py              # HTF bias (Daily+4H + 20-EMA)                           Task 9
src/v17/structure/engine.py            # StructureEngine orchestrator                           Task 10

tests/unit/structure/test_atr.py                                              Task 2
tests/unit/structure/test_smc_adapter.py                                      Task 3
tests/unit/structure/test_swings.py                                           Task 4
tests/unit/structure/test_fvg.py                                              Task 5
tests/unit/structure/test_ob.py                                               Task 6
tests/unit/structure/test_liquidity.py                                        Task 7
tests/unit/structure/test_mss.py                                              Task 8
tests/unit/structure/test_bias.py                                             Task 9
tests/unit/structure/test_engine.py                                           Task 10
tests/property/test_fvg_properties.py                                         Task 11
tests/property/test_ob_properties.py                                          Task 11
tests/integration/test_structure_real_data.py                                 Task 12
tests/fixtures/structure/*.csv                                                Tasks 5-10
```

---

## Task 1: Install `smartmoneyconcepts`, extend DTOs, add Protocol

**Files:**
- Modify: `src/v17/common/dtos.py` (add `Zone`, `Swing`, `Sweep`, `StructureSnapshot`)
- Create: `src/v17/structure/__init__.py`, `src/v17/structure/ports.py`
- Modify: `pyproject.toml` (add dep)
- Test: extend `tests/unit/common/test_dtos.py`

**Interfaces:**
- Produces: `Zone(kind: Literal["fvg","ob"], side: Side, tf: TF, created_at: datetime, top: Decimal, bottom: Decimal, mitigated_at: datetime | None = None)`.
- Produces: `Swing(kind: Literal["bos","choch","mss"], side: Side, tf: TF, at: datetime, price: Decimal)`.
- Produces: `Sweep(kind: Literal["bsl","ssl"], tf: TF, at: datetime, level: Decimal)`.
- Produces: `StructureSnapshot(symbol: Symbol, at: datetime, bias: Bias, zones: list[Zone], swings: list[Swing], sweeps: list[Sweep])`.
- Produces: `StructureEngine` Protocol: `def analyze(self, bars_by_tf: Mapping[TF, pd.DataFrame]) -> StructureSnapshot`.

- [ ] **Step 1: Add `smartmoneyconcepts` to `pyproject.toml` deps**

```toml
# in [project].dependencies, add:
"smartmoneyconcepts>=0.0.26",
```

- [ ] **Step 2: Install it + smoke import**

Run:
```
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -c "from smartmoneyconcepts import smc; print('ok', dir(smc)[:5])"
```
Expected: prints `ok [...]` with no error. If import fails (pandas 3.1 incompat), rule: pin pandas back to `<3.0` OR port needed functions manually. Record ruling in ledger.

- [ ] **Step 3: Write failing DTO tests**

Append to `tests/unit/common/test_dtos.py`:

```python
from v17.common.dtos import Zone, Swing, Sweep, StructureSnapshot
from v17.common.types import Bias

def test_zone_requires_top_ge_bottom() -> None:
    with pytest.raises(ValidationError):
        Zone(kind="fvg", side=Side.BUY, tf=TF.M15, created_at=_utc(2026,1,1),
             top=Decimal("1.0"), bottom=Decimal("1.1"))

def test_swing_fields() -> None:
    s = Swing(kind="bos", side=Side.BUY, tf=TF.M15,
              at=_utc(2026,1,1), price=Decimal("1.1"))
    assert s.kind == "bos"

def test_sweep_fields() -> None:
    s = Sweep(kind="bsl", tf=TF.M15, at=_utc(2026,1,1), level=Decimal("1.2"))
    assert s.kind == "bsl"

def test_snapshot_round_trip() -> None:
    snap = StructureSnapshot(
        symbol=Symbol("EURUSD"), at=_utc(2026,1,1),
        bias=Bias.BULL, zones=[], swings=[], sweeps=[],
    )
    assert snap.bias == Bias.BULL
```

Also add `from v17.common.types import Side` to test imports.

- [ ] **Step 4: Verify FAIL**

Run: `.venv\Scripts\pytest tests/unit/common -q`
Expected: ImportError on `Zone`.

- [ ] **Step 5: Implement DTO additions in `src/v17/common/dtos.py`**

Append after existing classes:

```python
from v17.common.types import Bias


class Zone(_Frozen):
    kind: Literal["fvg", "ob"]
    side: Side
    tf: TF
    created_at: datetime
    top: Decimal
    bottom: Decimal
    mitigated_at: datetime | None = None

    @field_validator("created_at", "mitigated_at")
    @classmethod
    def _ts_utc_opt(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _require_utc(v)

    @model_validator(mode="after")
    def _top_ge_bottom(self) -> Zone:
        if self.top < self.bottom:
            raise ValueError("top must be >= bottom")
        return self


class Swing(_Frozen):
    kind: Literal["bos", "choch", "mss"]
    side: Side
    tf: TF
    at: datetime
    price: Decimal

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


class Sweep(_Frozen):
    kind: Literal["bsl", "ssl"]
    tf: TF
    at: datetime
    level: Decimal

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


class StructureSnapshot(_Frozen):
    symbol: Symbol
    at: datetime
    bias: Bias
    zones: list[Zone]
    swings: list[Swing]
    sweeps: list[Sweep]

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)
```

- [ ] **Step 6: Implement `src/v17/structure/ports.py`**

```python
from __future__ import annotations
from collections.abc import Mapping
from typing import Protocol
import pandas as pd
from v17.common.dtos import StructureSnapshot
from v17.common.types import TF


class StructureEngine(Protocol):
    def analyze(self, bars_by_tf: Mapping[TF, pd.DataFrame]) -> StructureSnapshot: ...
```

- [ ] **Step 7: PASS**

Run: `.venv\Scripts\pytest tests/unit/common -q && .venv\Scripts\mypy src && .venv\Scripts\ruff check src tests`
Expected: all green; +4 DTO tests pass.

---

## Task 2: ATR (Wilder, 14)

**Files:**
- Create: `src/v17/structure/atr.py`
- Test: `tests/unit/structure/test_atr.py`

**Interfaces:**
- Produces: `atr(df: pd.DataFrame, period: int = 14) -> pd.Series`. Input: df with `high`, `low`, `close` float64 columns. Output: Series aligned to df.index, dtype float64, first `period-1` values are NaN.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/structure/test_atr.py
import numpy as np
import pandas as pd
from v17.structure.atr import atr

def _hlc(n: int, hi: float = 1.1, lo: float = 1.0, cl: float = 1.05) -> pd.DataFrame:
    return pd.DataFrame({"high": np.full(n, hi), "low": np.full(n, lo), "close": np.full(n, cl)})

def test_atr_length_and_nans() -> None:
    out = atr(_hlc(30), period=14)
    assert len(out) == 30
    assert out.iloc[:13].isna().all()
    assert not out.iloc[13:].isna().any()

def test_atr_constant_range() -> None:
    out = atr(_hlc(30, hi=1.10, lo=1.00, cl=1.05), period=14)
    # TR = 0.10 every bar; Wilder ATR converges to 0.10
    assert np.isclose(out.iloc[-1], 0.10)

def test_atr_rising_range() -> None:
    df = pd.DataFrame({
        "high":  np.arange(30, dtype=float) * 0.001 + 1.10,
        "low":   np.arange(30, dtype=float) * 0.001 + 1.00,
        "close": np.arange(30, dtype=float) * 0.001 + 1.05,
    })
    out = atr(df, period=14)
    assert out.iloc[-1] > out.iloc[14]
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement `src/v17/structure/atr.py`**

```python
from __future__ import annotations
import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].to_numpy(dtype="float64")
    low = df["low"].to_numpy(dtype="float64")
    close = df["close"].to_numpy(dtype="float64")
    prev_close = np.concatenate(([np.nan], close[:-1]))
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    out = np.full(len(df), np.nan)
    if len(df) < period:
        return pd.Series(out, index=df.index, name="atr")
    # Wilder: first value = simple mean of first `period` TR; then RMA
    first = np.nanmean(tr[:period])
    out[period - 1] = first
    for i in range(period, len(df)):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return pd.Series(out, index=df.index, name="atr")
```

- [ ] **Step 4: PASS**

Run: `.venv\Scripts\pytest tests/unit/structure/test_atr.py -q`
Expected: 3 passed.

---

## Task 3: smartmoneyconcepts adapter

**Files:**
- Create: `src/v17/structure/smc_adapter.py`
- Test: `tests/unit/structure/test_smc_adapter.py`

**Interfaces:**
- Produces: `prepare_smc_df(df: pd.DataFrame) -> pd.DataFrame`. Takes our canonical columns `[ts, open, high, low, close, volume, spread_pips]` and returns a DataFrame indexed by `ts` with columns `[open, high, low, close, volume]` typed for `smartmoneyconcepts.smc` (float64 OHLC, int volume).
- Produces: `smc_swing_highs_lows(df, swing_length=10) -> pd.DataFrame` passthrough to `smc.swing_highs_lows(df, swing_length=10)`. Documented wrapper so we isolate the dependency.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/structure/test_smc_adapter.py
import pandas as pd
import numpy as np
from v17.structure.smc_adapter import prepare_smc_df, smc_swing_highs_lows

def _ohlcv(n: int = 50) -> pd.DataFrame:
    ts = pd.date_range("2024-06-01", periods=n, freq="15min", tz="UTC")
    rng = np.random.default_rng(42)
    base = 1.10 + np.cumsum(rng.normal(0, 0.0005, n))
    return pd.DataFrame({
        "ts": ts, "open": base, "high": base + 0.0005,
        "low": base - 0.0005, "close": base + rng.normal(0, 0.0001, n),
        "volume": np.ones(n, dtype="int64"),
        "spread_pips": np.full(n, 0.8),
    })

def test_prepare_shape() -> None:
    df = prepare_smc_df(_ohlcv(50))
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "ts"

def test_swing_highs_lows_returns_frame() -> None:
    df = prepare_smc_df(_ohlcv(100))
    out = smc_swing_highs_lows(df, swing_length=10)
    assert isinstance(out, pd.DataFrame)
    # smc returns at least HighLow + Level columns
    assert any("HighLow" in c or "Level" in c for c in out.columns)
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement `src/v17/structure/smc_adapter.py`**

```python
from __future__ import annotations
import pandas as pd
from smartmoneyconcepts import smc


def prepare_smc_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.set_index("ts")[["open", "high", "low", "close", "volume"]].copy()
    out = out.astype({"open": "float64", "high": "float64", "low": "float64",
                      "close": "float64", "volume": "int64"})
    return out


def smc_swing_highs_lows(df: pd.DataFrame, swing_length: int = 10) -> pd.DataFrame:
    return smc.swing_highs_lows(df, swing_length=swing_length)
```

- [ ] **Step 4: PASS**

If smartmoneyconcepts import fails due to pandas 3.1 breakage: ruling — pin `pandas<3.0` in pyproject, reinstall, rerun. Record in ledger.

---

## Task 4: Swings + BOS/CHoCH

**Files:**
- Create: `src/v17/structure/swings.py`
- Test: `tests/unit/structure/test_swings.py`

**Interfaces:**
- Produces: `detect_swings(df_tf: pd.DataFrame, tf: TF, swing_length: int = 10) -> list[Swing]`. Uses `smc.swing_highs_lows` + `smc.bos_choch` to return list of `Swing` DTOs with `kind ∈ {"bos","choch"}`.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/structure/test_swings.py
import numpy as np
import pandas as pd
from v17.common.types import TF
from v17.structure.swings import detect_swings

def _uptrend(n: int = 80) -> pd.DataFrame:
    ts = pd.date_range("2024-06-01", periods=n, freq="15min", tz="UTC")
    base = 1.10 + np.linspace(0, 0.01, n) + np.sin(np.arange(n)/5) * 0.001
    return pd.DataFrame({
        "ts": ts, "open": base, "high": base + 0.0005,
        "low": base - 0.0005, "close": base,
        "volume": np.ones(n, dtype="int64"),
        "spread_pips": np.full(n, 0.8),
    })

def test_detect_swings_returns_dtos() -> None:
    out = detect_swings(_uptrend(80), tf=TF.M15, swing_length=10)
    assert all(s.kind in {"bos", "choch"} for s in out)
    assert all(s.tf == TF.M15 for s in out)
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement `src/v17/structure/swings.py`**

```python
from __future__ import annotations
from decimal import Decimal
import pandas as pd
from smartmoneyconcepts import smc
from v17.common.dtos import Swing
from v17.common.types import TF, Side
from v17.structure.smc_adapter import prepare_smc_df


def detect_swings(df_tf: pd.DataFrame, tf: TF, swing_length: int = 10) -> list[Swing]:
    smc_df = prepare_smc_df(df_tf)
    swings = smc.swing_highs_lows(smc_df, swing_length=swing_length)
    boschoch = smc.bos_choch(smc_df, swings)
    out: list[Swing] = []
    for i, row in boschoch.iterrows():
        bos = row.get("BOS")
        choch = row.get("CHOCH")
        if pd.notna(bos):
            kind = "bos"
            side = Side.BUY if bos == 1 else Side.SELL
            level_val = row.get("Level")
        elif pd.notna(choch):
            kind = "choch"
            side = Side.BUY if choch == 1 else Side.SELL
            level_val = row.get("Level")
        else:
            continue
        out.append(Swing(
            kind=kind, side=side, tf=tf,
            at=i.to_pydatetime() if hasattr(i, "to_pydatetime") else i,
            price=Decimal(str(level_val)),
        ))
    return out
```

- [ ] **Step 4: PASS**

---

## Task 5: FVG detector

**Files:**
- Create: `src/v17/structure/fvg.py`
- Test: `tests/unit/structure/test_fvg.py`
- Fixture: `tests/fixtures/structure/fvg_bull.csv`, `fvg_bear.csv`

**Interfaces:**
- Produces: `detect_fvgs(df_tf: pd.DataFrame, tf: TF, max_age_bars: int = 30) -> list[Zone]`. Rules per glossary: bullish `low[i] > high[i-2]` → zone `[high[i-2], low[i]]`; bearish `high[i] < low[i-2]` → zone `[high[i], low[i-2]]`. `created_at = ts[i-2]` (the 1st bar of the imbalance). `mitigated_at` set to ts of first bar after creation whose range intersects the zone. Only zones with no mitigation OR age ≤ `max_age_bars` returned.

- [ ] **Step 1: Create fixtures**

`tests/fixtures/structure/fvg_bull.csv` — 5 bars; bar 2 low > bar 0 high. UTF-8 header `ts,open,high,low,close,volume,spread_pips`:
```
ts,open,high,low,close,volume,spread_pips
2024-06-01T00:00:00+00:00,1.1000,1.1010,1.0990,1.1005,1,0.8
2024-06-01T00:15:00+00:00,1.1005,1.1025,1.1000,1.1020,1,0.8
2024-06-01T00:30:00+00:00,1.1020,1.1040,1.1015,1.1035,1,0.8
2024-06-01T00:45:00+00:00,1.1035,1.1045,1.1030,1.1040,1,0.8
2024-06-01T01:00:00+00:00,1.1040,1.1050,1.1035,1.1045,1,0.8
```

`fvg_bear.csv` — mirror, 5 bars with bar 2 high < bar 0 low.

- [ ] **Step 2: Write failing test**

```python
# tests/unit/structure/test_fvg.py
from pathlib import Path
from decimal import Decimal
import pandas as pd
from v17.common.types import TF, Side
from v17.structure.fvg import detect_fvgs

FIX = Path(__file__).parent.parent.parent / "fixtures" / "structure"


def _load(name: str) -> pd.DataFrame:
    df = pd.read_csv(FIX / name)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df

def test_detect_bull_fvg() -> None:
    df = _load("fvg_bull.csv")
    zones = detect_fvgs(df, TF.M15)
    assert len(zones) >= 1
    z = zones[0]
    assert z.kind == "fvg" and z.side == Side.BUY and z.tf == TF.M15
    assert z.top == Decimal("1.1015") and z.bottom == Decimal("1.1010")

def test_detect_bear_fvg_count() -> None:
    df = _load("fvg_bear.csv")
    zones = detect_fvgs(df, TF.M15)
    assert any(z.side == Side.SELL for z in zones)
```

- [ ] **Step 3: Verify FAIL**

- [ ] **Step 4: Implement `src/v17/structure/fvg.py`**

```python
from __future__ import annotations
from decimal import Decimal
import pandas as pd
from v17.common.dtos import Zone
from v17.common.types import TF, Side


def detect_fvgs(df_tf: pd.DataFrame, tf: TF, max_age_bars: int = 30) -> list[Zone]:
    out: list[Zone] = []
    highs = df_tf["high"].to_numpy()
    lows = df_tf["low"].to_numpy()
    ts = df_tf["ts"].tolist()
    n = len(df_tf)
    for i in range(2, n):
        if lows[i] > highs[i - 2]:
            top = Decimal(str(lows[i]))
            bottom = Decimal(str(highs[i - 2]))
            z = Zone(kind="fvg", side=Side.BUY, tf=tf,
                     created_at=ts[i - 2].to_pydatetime(),
                     top=top, bottom=bottom)
            z = _apply_mitigation(z, df_tf, i, max_age_bars)
            if z is not None:
                out.append(z)
        elif highs[i] < lows[i - 2]:
            top = Decimal(str(lows[i - 2]))
            bottom = Decimal(str(highs[i]))
            z = Zone(kind="fvg", side=Side.SELL, tf=tf,
                     created_at=ts[i - 2].to_pydatetime(),
                     top=top, bottom=bottom)
            z = _apply_mitigation(z, df_tf, i, max_age_bars)
            if z is not None:
                out.append(z)
    return out


def _apply_mitigation(z: Zone, df: pd.DataFrame, created_idx: int, max_age_bars: int) -> Zone | None:
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    ts = df["ts"].tolist()
    top = float(z.top); bottom = float(z.bottom)
    for j in range(created_idx + 1, len(df)):
        if lows[j] <= top and highs[j] >= bottom:
            if (j - created_idx) <= max_age_bars:
                return z.model_copy(update={"mitigated_at": ts[j].to_pydatetime()})
            return None
    return z if (len(df) - 1 - created_idx) <= max_age_bars else None
```

- [ ] **Step 5: PASS**

---

## Task 6: OB detector

**Files:**
- Create: `src/v17/structure/ob.py`
- Test: `tests/unit/structure/test_ob.py`
- Fixture: `tests/fixtures/structure/ob_bull.csv`

**Interfaces:**
- Produces: `detect_obs(df_tf: pd.DataFrame, tf: TF, atr_mult: float = 2.0, max_age_bars: int = 30) -> list[Zone]`. OB = last opposite-color candle before a displacement candle whose body ≥ `atr_mult × ATR(14)`. Zone = full body of the OB candle. Mitigation + age rules per FVG.

- [ ] **Step 1: Create fixture `ob_bull.csv`** 20 bars: a down candle (opposite color) followed by a strong up candle (body ≥ 2×ATR), then meandering.

- [ ] **Step 2: Write failing test** verifying exactly one bullish OB zone emitted; zone bounds equal to OB candle's open/close.

- [ ] **Step 3: Implement**

```python
# src/v17/structure/ob.py
from __future__ import annotations
from decimal import Decimal
import pandas as pd
from v17.common.dtos import Zone
from v17.common.types import TF, Side
from v17.structure.atr import atr


def detect_obs(df_tf: pd.DataFrame, tf: TF, atr_mult: float = 2.0,
               max_age_bars: int = 30) -> list[Zone]:
    out: list[Zone] = []
    df = df_tf.reset_index(drop=True)
    atr_series = atr(df, period=14).to_numpy()
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    ts = df["ts"].tolist()
    for i in range(14, len(df)):
        body = abs(closes[i] - opens[i])
        if pd.isna(atr_series[i]) or atr_series[i] == 0:
            continue
        if body < atr_mult * atr_series[i]:
            continue
        bull_displacement = closes[i] > opens[i]
        # look back for the first opposite-color candle
        for k in range(i - 1, max(-1, i - 10), -1):
            opp = (closes[k] < opens[k]) if bull_displacement else (closes[k] > opens[k])
            if opp:
                side = Side.BUY if bull_displacement else Side.SELL
                top = Decimal(str(max(opens[k], closes[k])))
                bottom = Decimal(str(min(opens[k], closes[k])))
                z = Zone(kind="ob", side=side, tf=tf,
                         created_at=ts[k].to_pydatetime(),
                         top=top, bottom=bottom)
                z = _apply_mitigation(z, highs, lows, ts, k, max_age_bars)
                if z is not None:
                    out.append(z)
                break
    return out


def _apply_mitigation(z: Zone, highs, lows, ts, created_idx: int, max_age_bars: int):
    top = float(z.top); bottom = float(z.bottom)
    for j in range(created_idx + 1, len(highs)):
        if lows[j] <= top and highs[j] >= bottom:
            if (j - created_idx) <= max_age_bars:
                return z.model_copy(update={"mitigated_at": ts[j].to_pydatetime()})
            return None
    return z if (len(highs) - 1 - created_idx) <= max_age_bars else None
```

- [ ] **Step 4: PASS**

---

## Task 7: Liquidity + Sweep detector

**Files:**
- Create: `src/v17/structure/liquidity.py`
- Test: `tests/unit/structure/test_liquidity.py`
- Fixture: `tests/fixtures/structure/sweep_bsl.csv`, `sweep_ssl.csv`

**Interfaces:**
- Produces: `detect_sweeps(df_tf: pd.DataFrame, tf: TF, swing_length: int = 10) -> list[Sweep]`. BSL/SSL levels taken from `smc.swing_highs_lows`. Sweep = bar whose `high > level` AND `close < level` (BSL sweep) or `low < level` AND `close > level` (SSL sweep).

- [ ] **Step 1: Create fixtures.**

- [ ] **Step 2: Write failing test.** Verify at least one BSL sweep detected in `sweep_bsl.csv`.

- [ ] **Step 3: Implement.**

```python
# src/v17/structure/liquidity.py
from __future__ import annotations
from decimal import Decimal
import pandas as pd
from smartmoneyconcepts import smc
from v17.common.dtos import Sweep
from v17.common.types import TF
from v17.structure.smc_adapter import prepare_smc_df


def detect_sweeps(df_tf: pd.DataFrame, tf: TF, swing_length: int = 10) -> list[Sweep]:
    smc_df = prepare_smc_df(df_tf)
    swings = smc.swing_highs_lows(smc_df, swing_length=swing_length)
    out: list[Sweep] = []
    levels: list[tuple[pd.Timestamp, float, int]] = []
    for idx, row in swings.iterrows():
        hl = row.get("HighLow")
        if pd.notna(hl):
            levels.append((idx, float(row.get("Level")), int(hl)))
    # evaluate every bar after each level
    for lvl_ts, lvl_price, hl in levels:
        after = df_tf[df_tf["ts"] > lvl_ts]
        for _, bar in after.iterrows():
            if hl == 1:  # swing high → BSL
                if bar["high"] > lvl_price and bar["close"] < lvl_price:
                    out.append(Sweep(kind="bsl", tf=tf,
                                     at=bar["ts"].to_pydatetime(),
                                     level=Decimal(str(lvl_price))))
                    break
            else:  # swing low → SSL
                if bar["low"] < lvl_price and bar["close"] > lvl_price:
                    out.append(Sweep(kind="ssl", tf=tf,
                                     at=bar["ts"].to_pydatetime(),
                                     level=Decimal(str(lvl_price))))
                    break
    return out
```

- [ ] **Step 4: PASS**

---

## Task 8: MSS detector (1m)

**Files:**
- Create: `src/v17/structure/mss.py`
- Test: `tests/unit/structure/test_mss.py`

**Interfaces:**
- Produces: `detect_mss(df_1m: pd.DataFrame, zones_15m: list[Zone], atr_mult: float = 1.5) -> list[Swing]`. MSS = a CHoCH on 1m (via `smc.bos_choch` on 1m swings with swing_length=10) that occurs inside at least one unmitigated 15m FVG or OB zone AND whose confirming candle has `abs(close-open) > atr_mult × ATR(14, 1m)`.

- [ ] **Step 1: Write failing test** with a hand-constructed 1m sequence inside a bullish zone, ending with a strong bullish body after a CHoCH; expect one MSS.

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement.** Reuse `detect_swings` from Task 4, filter CHoCH only, filter by in-zone + body threshold.

```python
# src/v17/structure/mss.py
from __future__ import annotations
import pandas as pd
from v17.common.dtos import Swing, Zone
from v17.common.types import TF
from v17.structure.atr import atr
from v17.structure.swings import detect_swings


def _in_zone(price: float, zones: list[Zone]) -> bool:
    for z in zones:
        if z.mitigated_at is not None:
            continue
        if float(z.bottom) <= price <= float(z.top):
            return True
    return False


def detect_mss(df_1m: pd.DataFrame, zones_15m: list[Zone], atr_mult: float = 1.5) -> list[Swing]:
    atr_series = atr(df_1m, period=14)
    choches = [s for s in detect_swings(df_1m, TF.M1, swing_length=10) if s.kind == "choch"]
    out: list[Swing] = []
    ts_index: dict = {t.to_pydatetime(): i for i, t in enumerate(df_1m["ts"])}
    for s in choches:
        i = ts_index.get(s.at)
        if i is None:
            continue
        body = abs(float(df_1m["close"].iloc[i]) - float(df_1m["open"].iloc[i]))
        a = atr_series.iloc[i]
        if pd.isna(a) or body < atr_mult * a:
            continue
        price = float(df_1m["close"].iloc[i])
        if not _in_zone(price, zones_15m):
            continue
        out.append(Swing(kind="mss", side=s.side, tf=TF.M1, at=s.at, price=s.price))
    return out
```

- [ ] **Step 4: PASS**

---

## Task 9: HTF bias (Daily + 4H)

**Files:**
- Create: `src/v17/structure/bias.py`
- Test: `tests/unit/structure/test_bias.py`

**Interfaces:**
- Produces: `compute_bias(df_1d: pd.DataFrame, df_4h: pd.DataFrame) -> Bias`. Rule: `BULL` iff last 4H structure sign (from `detect_swings` latest BOS/CHoCH) is BUY AND Daily close > Daily 20-EMA on last Daily bar. `BEAR` symmetric. Else `NONE`.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/structure/test_bias.py
import numpy as np
import pandas as pd
from v17.common.types import Bias
from v17.structure.bias import compute_bias

def _frame(n: int, start: str, freq: str, drift: float) -> pd.DataFrame:
    ts = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    base = 1.10 + np.linspace(0, drift, n) + np.sin(np.arange(n)/4)*0.001
    return pd.DataFrame({
        "ts": ts, "open": base, "high": base + 0.001, "low": base - 0.001, "close": base,
        "volume": np.ones(n, dtype="int64"),
        "spread_pips": np.full(n, 0.8),
    })

def test_bullish_bias() -> None:
    daily = _frame(50, "2024-04-01", "1D", drift=+0.02)
    four_h = _frame(240, "2024-04-01", "4h", drift=+0.015)
    assert compute_bias(daily, four_h) == Bias.BULL

def test_bearish_bias() -> None:
    daily = _frame(50, "2024-04-01", "1D", drift=-0.02)
    four_h = _frame(240, "2024-04-01", "4h", drift=-0.015)
    assert compute_bias(daily, four_h) == Bias.BEAR
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement.**

```python
# src/v17/structure/bias.py
from __future__ import annotations
import pandas as pd
from v17.common.types import Bias, Side, TF
from v17.structure.swings import detect_swings


def compute_bias(df_1d: pd.DataFrame, df_4h: pd.DataFrame) -> Bias:
    if len(df_1d) < 20 or len(df_4h) < 20:
        return Bias.NONE
    ema20 = df_1d["close"].ewm(span=20, adjust=False).mean()
    last_close = float(df_1d["close"].iloc[-1])
    daily_bull = last_close > float(ema20.iloc[-1])

    swings_4h = detect_swings(df_4h, TF.H4, swing_length=10)
    if not swings_4h:
        return Bias.NONE
    last_4h = swings_4h[-1]
    four_h_bull = last_4h.side == Side.BUY

    if daily_bull and four_h_bull:
        return Bias.BULL
    if (not daily_bull) and (not four_h_bull):
        return Bias.BEAR
    return Bias.NONE
```

- [ ] **Step 4: PASS**

---

## Task 10: StructureEngine orchestrator

**Files:**
- Create: `src/v17/structure/engine.py`
- Test: `tests/unit/structure/test_engine.py`

**Interfaces:**
- Produces: `DefaultStructureEngine` class with `analyze(bars_by_tf: Mapping[TF, pd.DataFrame]) -> StructureSnapshot`. Required TFs in input: `TF.D1`, `TF.H4`, `TF.M15`, `TF.M1`. `at` = last 1m bar timestamp. Zones = FVG(15m) ∪ OB(15m). Swings = BOS/CHoCH(4H) ∪ MSS(1m, filtered by 15m zones). Sweeps = BSL/SSL(15m).

- [ ] **Step 1: Write failing test** feeding fabricated 4-TF data and asserting a non-empty snapshot with expected fields.

- [ ] **Step 2: Implement.**

```python
# src/v17/structure/engine.py
from __future__ import annotations
from collections.abc import Mapping
import pandas as pd
from v17.common.dtos import StructureSnapshot
from v17.common.errors import V17StructureError
from v17.common.types import TF, Symbol
from v17.structure.bias import compute_bias
from v17.structure.fvg import detect_fvgs
from v17.structure.ob import detect_obs
from v17.structure.liquidity import detect_sweeps
from v17.structure.mss import detect_mss
from v17.structure.swings import detect_swings


REQUIRED_TFS = (TF.D1, TF.H4, TF.M15, TF.M1)


class DefaultStructureEngine:
    def __init__(self, symbol: Symbol) -> None:
        self.symbol = symbol

    def analyze(self, bars_by_tf: Mapping[TF, pd.DataFrame]) -> StructureSnapshot:
        for tf in REQUIRED_TFS:
            if tf not in bars_by_tf:
                raise V17StructureError("missing TF", tf=tf)
        df_1d = bars_by_tf[TF.D1]
        df_4h = bars_by_tf[TF.H4]
        df_15m = bars_by_tf[TF.M15]
        df_1m = bars_by_tf[TF.M1]
        bias = compute_bias(df_1d, df_4h)
        zones = detect_fvgs(df_15m, TF.M15) + detect_obs(df_15m, TF.M15)
        swings_4h = detect_swings(df_4h, TF.H4, swing_length=10)
        mss_1m = detect_mss(df_1m, zones)
        sweeps = detect_sweeps(df_15m, TF.M15, swing_length=10)
        at = df_1m["ts"].iloc[-1].to_pydatetime()
        return StructureSnapshot(
            symbol=self.symbol, at=at, bias=bias,
            zones=zones, swings=swings_4h + mss_1m, sweeps=sweeps,
        )
```

- [ ] **Step 3: PASS**

---

## Task 11: Property-based tests

**Files:**
- Create: `tests/property/test_fvg_properties.py`, `test_ob_properties.py`

**Interfaces:** None new. Hypothesis strategies.

- [ ] **Step 1: Implement**

```python
# tests/property/test_fvg_properties.py
import pandas as pd
import numpy as np
from hypothesis import given, strategies as st, settings
from v17.common.types import TF
from v17.structure.fvg import detect_fvgs


@st.composite
def ohlc_frame(draw, min_bars=20, max_bars=100):
    n = draw(st.integers(min_bars, max_bars))
    ts = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    base = 1.10 + np.cumsum(draw(st.lists(st.floats(-0.001, 0.001), min_size=n, max_size=n)))
    highs = base + np.abs(draw(st.lists(st.floats(0, 0.0005), min_size=n, max_size=n)))
    lows = base - np.abs(draw(st.lists(st.floats(0, 0.0005), min_size=n, max_size=n)))
    opens = base
    closes = base + draw(st.lists(st.floats(-0.0003, 0.0003), min_size=n, max_size=n))
    return pd.DataFrame({"ts": ts, "open": opens, "high": highs,
                         "low": lows, "close": closes,
                         "volume": np.ones(n, dtype="int64"),
                         "spread_pips": np.full(n, 0.8)})


@settings(deadline=None, max_examples=25)
@given(ohlc_frame())
def test_fvg_zones_have_top_gt_bottom(df: pd.DataFrame) -> None:
    for z in detect_fvgs(df, TF.M15):
        assert z.top > z.bottom

@settings(deadline=None, max_examples=25)
@given(ohlc_frame())
def test_fvg_zones_timestamps_utc(df: pd.DataFrame) -> None:
    for z in detect_fvgs(df, TF.M15):
        assert z.created_at.tzinfo is not None
```

(Same pattern for `test_ob_properties.py`.)

- [ ] **Step 2: PASS**

---

## Task 12: Real-data integration smoke

**Files:**
- Create: `tests/integration/test_structure_real_data.py`

**Interfaces:** None new.

- [ ] **Step 1: Write test**

```python
# tests/integration/test_structure_real_data.py
from datetime import UTC, datetime
from pathlib import Path
import pytest
from v17.common.types import TF, Symbol
from v17.data.providers import ParquetBarProvider
from v17.structure.engine import DefaultStructureEngine
import pandas as pd


@pytest.mark.integration
def test_structure_on_real_eurusd_london_session() -> None:
    pq = Path("data/parquet")
    if not (pq / "EURUSD").exists():
        pytest.skip("real data not ingested")
    p = ParquetBarProvider(pq)
    # pick a known London session: 2024-06-03 London killzone
    def _bars(tf: TF, start_h: int, end_h: int) -> pd.DataFrame:
        bars = list(p.bars(Symbol("EURUSD"), tf,
                           datetime(2024, 6, 3, start_h, tzinfo=UTC),
                           datetime(2024, 6, 3, end_h, tzinfo=UTC)))
        return pd.DataFrame([b.model_dump() for b in bars])

    bars_by_tf = {
        TF.D1: _bars(TF.D1, 0, 23),
        TF.H4: _bars(TF.H4, 0, 23),
        TF.M15: _bars(TF.M15, 0, 23),
        TF.M1: _bars(TF.M1, 7, 10),  # London killzone 07:00-10:00 London = 06:00-09:00 UTC in BST
    }
    # Need wider HTF windows
    bars_by_tf[TF.D1] = pd.DataFrame([b.model_dump() for b in p.bars(Symbol("EURUSD"), TF.D1,
                                     datetime(2024, 3, 1, tzinfo=UTC), datetime(2024, 6, 3, 23, tzinfo=UTC))])
    bars_by_tf[TF.H4] = pd.DataFrame([b.model_dump() for b in p.bars(Symbol("EURUSD"), TF.H4,
                                     datetime(2024, 5, 1, tzinfo=UTC), datetime(2024, 6, 3, 23, tzinfo=UTC))])
    for tf in bars_by_tf:
        for col in ("open","high","low","close","spread_pips"):
            bars_by_tf[tf][col] = bars_by_tf[tf][col].astype(float)

    eng = DefaultStructureEngine(symbol=Symbol("EURUSD"))
    snap = eng.analyze(bars_by_tf)
    # smoke assertions only — we are not validating edge, just non-crash + sane shapes
    assert snap.symbol == Symbol("EURUSD")
    assert snap.bias.value in {"bull", "bear", "none"}
    print(f"bias={snap.bias} zones={len(snap.zones)} swings={len(snap.swings)} sweeps={len(snap.sweeps)}")
```

Register marker in `pyproject.toml`:
```
[tool.pytest.ini_options]
...
markers = ["integration: hits real data"]
```

- [ ] **Step 2: Run**

Run: `.venv\Scripts\pytest tests/integration -m integration -s`
Expected: passes with printed snapshot stats.

---

## Self-review

- Spec §7 M2 items 1-7: covered by Tasks 2-10.
- Property tests: Task 11.
- Hand-crafted fixtures from `SrsBlack/ict-knowledge-library`: fixtures in Tasks 5-10 encode canonical examples; a future enhancement can import the library's examples wholesale.
- 100% deterministic: all detectors are pure functions over DataFrames.
- Type consistency: `Zone`, `Swing`, `Sweep`, `StructureSnapshot` names match `docs/API.md` §2.

## Done definition

- All 12 tasks pass tests.
- `.venv\Scripts\ruff check src tests` clean.
- `.venv\Scripts\mypy src` clean.
- Coverage ≥ 85% on `src/v17/structure/`.
- Integration smoke passes on real EURUSD 2024-06-03 London killzone with no crash.
- Snapshot report prints non-zero zones + at least one swing.
