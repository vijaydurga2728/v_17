# Data Ingest Gap Analysis

**Date:** 2026-11-03  
**Target file:** `src/v17/data/dukascopy_csv.py`  
**Reference:** Plan Task 2.2 + Spec §8.1 bid/ask paired model

---

## Current capabilities

The existing loader (`src/v17/data/dukascopy_csv.py`) provides:

- **Header parsing:** `parse_header(path)` reads CSV first line, strips quotes and whitespace
- **Time format detection:** `_detect_time_format(cols)` identifies three Dukascopy export formats:
  - "Gmt time" (UTC, strptime `%d.%m.%Y %H:%M:%S.%f`)
  - "Local time" (timezone in string, strptime `%d.%m.%Y %H:%M:%S.%f%z`)
  - "Time (EET)" (Europe/Helsinki TZ, strptime `%Y.%m.%d %H:%M:%S`)
- **Single-file OHLCV read:** `read_file(path, side: "bid"|"ask")` loads one CSV, renames columns `Open/High/Low/Close → open_{side}/high_{side}/low_{side}/close_{side}`, converts time to UTC `ts`, coerces Volume to float64, deduplicates by `ts`, sorts, returns DataFrame with `[ts, open_{side}, high_{side}, low_{side}, close_{side}, volume]`
- **Timezone conversion:** EET → UTC conversion via `pd.to_datetime(naive).tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")`
- **Pip scaling:** `_pip_scale(price, symbol)` returns 10000 (FX majors), 100 (JPY pairs), 1 (indices/commodities)
- **Stitching two files:** `stitch_pair(bid_paths, ask_paths, symbol)` concatenates multiple bid/ask file lists, deduplicates separately, merges on `ts` (inner join, one-to-one validated), computes midpoint OHLC, computes `spread_pips = (close_ask - close_bid) * scale`, returns single output DataFrame with `[ts, open, high, low, close, volume, spread_pips]`

**Output schema (current `stitch_pair`):**
```
ts (UTC datetime),
open, high, low, close (float64 midpoint OHLC),
volume (int64),
spread_pips (float64)
```

**Assumptions:**
- Single CSV per side (bid/ask), or multiple CSVs per side concatenated before stitching
- Both sides have exactly matching timestamps after dedup
- Volume column in source CSVs can be float or int; coerced to float64 pre-stitch

---

## Missing capabilities for Spec §8.1

Spec §8.1 requires:

> Dukascopy-sourced CSVs are paired per instrument: one bid file, one ask file, both EET-timezone 1-minute bars with OHLCV. Ingest pipeline joins them on `time (EET)` and converts to UTC.
>
> Per-bar output schema (Parquet):
> ```
> ts_utc (int64 nanoseconds UTC), symbol (categorical),
> bid_o, bid_h, bid_l, bid_c (float64),
> ask_o, ask_h, ask_l, ask_c (float64),
> bid_volume, ask_volume (float64),
> spread_mid (float64 = ask_c - bid_c)
> ```

### List of missing capabilities:

1. **Paired bid/ask column preservation in output:** Current `stitch_pair` computes midpoint OHLC and discards individual bid/ask prices. Spec §8.1 requires output preserves all eight price columns: `bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c`.

2. **Dual-volume tracking:** Current code collapses volume to one column post-stitch. Spec requires `bid_volume, ask_volume` (float64) as separate columns.

3. **Time precision (nanosecond UTC):** Current code uses pandas Timestamp UTC. Output schema must be int64 nanoseconds since epoch for Parquet strict schema.

4. **Symbol column in output:** Current `stitch_pair` takes a symbol parameter but does not include it in the output DataFrame. Spec output schema requires `symbol (categorical)`.

5. **Column naming:** Current output has `spread_pips`. Spec requires `spread_mid` defined as `float64 = ask_c - bid_c` (price delta, not pip count). The spec does not output a pip-scaled spread; spread is output as raw price delta.

6. **Function signature for flexible ingest:** Current `stitch_pair(bid_paths: list, ask_paths: list, symbol)` assumes pre-paired lists. Spec brief mentions `load_paired_bars(bid_path, ask_path, symbol) -> pd.DataFrame` for single-file-pair loads. No function signature for flexible file discovery or multi-symbol batch load.

7. **Data type guarantees for Parquet:** Current code uses pandas defaults. Output must guarantee exact dtype match: `ts_utc (int64 ns), symbol (string/categorical), bid_o/ask_o etc (float64), volumes (float64)` before Parquet serialization.

---

## Required changes

### File-level patches needed by Task 2.2

**Function 1: Refactor `stitch_pair` to preserve paired bid/ask columns**

Signature:
```python
def stitch_pair(
    bid_paths: list[Path], 
    ask_paths: list[Path], 
    symbol: str | None = None
) -> pd.DataFrame:
    """
    Stitch paired bid/ask CSVs into a single DataFrame with full bid/ask price columns.
    
    Returns DataFrame with columns:
      ts_utc (int64 ns UTC), symbol (str), 
      bid_o, bid_h, bid_l, bid_c (float64),
      ask_o, ask_h, ask_l, ask_c (float64),
      bid_volume, ask_volume (float64),
      spread_mid (float64 = ask_c - bid_c)
    """
```

Changes required:
- Keep separate `bid_df` and `ask_df` frames through merge
- Preserve all bid/ask columns: rename to `bid_o`, `bid_h`, `bid_l`, `bid_c` for bid side; `ask_o`, `ask_h`, `ask_l`, `ask_c` for ask side
- Rename volume columns to `bid_volume` and `ask_volume` (with suffix merge, e.g., `bid_df.columns = [..., "bid_volume"]` before merge)
- Compute `spread_mid = ask_c - bid_c` as float64 (raw price, not pips)
- Add `symbol` column with constant value (from parameter, defaulting to None → string "None")
- Convert `ts` to int64 nanoseconds: `pd.to_datetime(ts_utc).astype('int64')` (already UTC at this point)
- Cast `symbol` to categorical dtype
- Select final output columns in spec order: `[ts_utc, symbol, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, bid_volume, ask_volume, spread_mid]`

**Function 2: Add new `load_paired_bars(bid_path, ask_path, symbol)`**

Signature:
```python
def load_paired_bars(bid_path: Path, ask_path: Path, symbol: str) -> pd.DataFrame:
    """
    Load a single pair of bid/ask CSV files and return stitched paired DataFrame.
    
    Convenience wrapper around stitch_pair for single-file-pair loads.
    
    Returns: DataFrame with columns as per spec §8.1
    """
```

Implementation:
- Call `stitch_pair([bid_path], [ask_path], symbol)`
- Return result

**Function 3: Optional refactor `read_file` to track column side metadata**

Current `read_file(path, side)` renames columns immediately. Consider:
- Keep original column names longer in parse flow (to clarify which side they come from)
- OR: document clearly in docstring that `volume` column is renamed to `{side}_volume` by caller before merge

**Function 4: Update `_detect_time_format` to validate EET expectation (optional robustness)**

Current code accepts any of three time formats. If spec hardcodes EET for Dukascopy in this cycle:
- Add optional validation flag to reject non-EET formats
- OR: add a new function `_detect_time_format_strict(cols)` that enforces EET only

---

## Risks

1. **Breaking change to `stitch_pair` return schema:** Existing code calling `stitch_pair(...)` expecting midpoint OHLC will break. Current output has `[ts, open, high, low, close, volume, spread_pips]`; new output has `[ts_utc, symbol, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, bid_volume, ask_volume, spread_mid]`. If any existing caller depends on the old schema, it will error on column lookup.
   - **Mitigation:** Grep for `stitch_pair` calls in the codebase before refactor. Likely only called during data-prep phase, not in production FSM code. Check `src/v17/backtest/` and `src/v17/live/` for usage.

2. **Type change to `spread_mid` (price delta vs pips):** Current code outputs `spread_pips` (already scaled by pip count). New spec requires `spread_mid` as raw price delta. Downstream code expecting pips will break.
   - **Mitigation:** Any downstream cost model (e.g., slippage calculation) must convert `spread_mid` back to pips using `_pip_scale()` if needed. Update callers to do so.

3. **Volume semantics:** Current `stitch_pair` outputs single `volume` (ambiguous which side). Spec separates `bid_volume, ask_volume`. If downstream uses volume for position-sizing diagnostics, behavior may change.
   - **Mitigation:** Document which volume is used for risk calculations (likely bid for short entries, ask for long entries, or context-dependent). Cost model §8 remains the source of truth.

4. **Symbol column as categorical dtype:** pandas categorical requires careful handling in Parquet serialization and aggregation. Ensure Parquet schema supports categorical or convert to string before write.
   - **Mitigation:** Test Parquet round-trip with `to_parquet(..., dtype={'symbol': 'string'})` or explicit categorical encoding.

5. **Existing test coverage:** If `tests/` has tests for `stitch_pair`, they will fail on column mismatch. Unit tests will need update.
   - **Mitigation:** Review `tests/unit/backtest/` and `tests/unit/data/` for existing `dukascopy_csv` tests. Update assertions to match new schema.

6. **Time precision (nanoseconds):** Current code may lose sub-microsecond precision in conversion. Dukascopy export is to millisecond precision (`.%f` = microseconds in format string). Conversion to int64 ns should be safe, but verify no rounding errors in pd.to_datetime().astype('int64').
   - **Mitigation:** Unit test: load sample CSV, convert to int64 ns, convert back, verify round-trip preserves original timestamp.

