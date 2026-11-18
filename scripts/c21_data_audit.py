"""Cycle 21 data-integrity audit (spec §12, D15, R20). Reads development M1 data only; runs NO strategy logic.

Writes out/c21/data_audit.json and out/c21/data_audit.md.
"""

# ruff: noqa: E402, PLR0915
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.smc_sb.config import INSTRUMENTS
from v17.smc_sb.data import (
    FIELDS,
    DataIntegrityError,
    Market,
    build_market,
    crossed_mask,
    frozen_side_mask,
    load_m1,
    source_files,
    validate_m1,
)
from v17.smc_sb.session import NS_PER_MIN, ny_ns, trading_date_of, xnys_dates

OUT = REPO / "out" / "c21"
DEV_FIRST, DEV_LAST = "2018-01-01", "2024-12-31"


def raw_checks(df: pd.DataFrame) -> dict[str, int]:
    out = {"rows": len(df), "duplicate_ts": int(df.ts_utc.duplicated().sum())}
    px = df[[f"{s}_{f}" for s in ("bid", "ask") for f in FIELDS]]
    out["nan_prices"] = int(px.isna().to_numpy().sum())
    out["non_positive_prices"] = int((px <= 0).to_numpy().sum())
    for f in FIELDS:
        out[f"crossed_{f}"] = int((df[f"ask_{f}"] < df[f"bid_{f}"]).sum())
    for s in ("bid", "ask"):
        bad = (df[f"{s}_h"] < df[[f"{s}_o", f"{s}_c", f"{s}_l"]].max(axis=1)) | (
            df[f"{s}_l"] > df[[f"{s}_o", f"{s}_c"]].min(axis=1)
        )
        out[f"inconsistent_{s}_ohlc"] = int(bad.sum())
    wall = pd.to_datetime(df.ts_utc, unit="ns", utc=True).dt.tz_convert("America/New_York")
    crossed = np.zeros(len(df), dtype=bool)
    for f in FIELDS:
        crossed |= (df[f"ask_{f}"] < df[f"bid_{f}"]).to_numpy()
    out["crossed_bar_ny_dates"] = sorted({str(x.date()) for x in wall[crossed]})
    out["crossed_bars_in_0930_1600"] = int(
        (crossed & ((wall.dt.hour * 60 + wall.dt.minute).between(570, 959)).to_numpy()).sum()
    )
    mins = (wall.dt.hour * 60 + wall.dt.minute).to_numpy()
    win = (mins >= 570) & (mins < 665)
    pxa = df[[f"{s}_{f}" for s in ("bid", "ask") for f in FIELDS]]
    rep = (pxa.diff().abs().sum(axis=1) == 0).to_numpy()
    out["window_0930_1105_bars"] = int(win.sum())
    out["window_bars_identical_to_previous"] = int((rep & win).sum())
    out["saturday_bars"] = int((wall.dt.dayofweek == 5).sum())
    out["sunday_before_17_bars"] = int(((wall.dt.dayofweek == 6) & (wall.dt.hour < 17)).sum())
    return out


def audit(name: str, dates: list[dt.date]) -> tuple[dict[str, object], Market | None]:
    df = load_m1(name)
    rep: dict[str, object] = {
        "symbol": INSTRUMENTS[name],
        "files": len(source_files(name)),
        **raw_checks(df),
    }
    try:
        validate_m1(df)
        rep["validate_m1"] = "pass"
    except DataIntegrityError as e:
        rep["validate_m1"] = f"FAIL: {e}"
        return rep, None
    mk = build_market(name, df)
    # R27: map every crossed bar to its 17:00-17:00 trading date (computed, not hardcoded)
    cm = crossed_mask(df.sort_values("ts_utc").reset_index(drop=True))
    td = trading_date_of(df.sort_values("ts_utc").ts_utc.to_numpy(np.int64)[cm])
    rep["r27_crossed_bars_by_session"] = {
        str(k): int(v) for k, v in pd.Series(td.astype(str)).value_counts().sort_index().items()
    }
    rep["r27_excluded_sessions"] = [
        f"{d.isoformat()} ({mk.exclusion_reason.get(d, '')})" for d in mk.excluded_sessions
    ]
    rep["r31_frozen_side_bars"] = int(
        frozen_side_mask(df.sort_values("ts_utc").reset_index(drop=True), 30).sum()
    )
    lo_d, hi_d = dt.date.fromisoformat(DEV_FIRST), dt.date.fromisoformat(DEV_LAST)
    rep["r28_early_close_dates"] = sorted(
        d.isoformat() for d in mk.early_close if lo_d <= d <= hi_d
    )
    rep["r29_non_xnys_sessions"] = [
        d.isoformat() for d in mk.non_xnys_sessions if lo_d <= d <= hi_d
    ]
    rep["r30_repeated_bars_total"] = int(mk.repeat.sum())
    t = pd.to_datetime(mk.ts, unit="ns", utc=True).tz_convert("America/New_York")
    rep["first_bar_ny"], rep["last_bar_ny"] = str(t[0]), str(t[-1])
    rep["rows_per_year"] = {
        str(y): int(n) for y, n in pd.Series(t.year).value_counts().sort_index().items()
    }

    miss_win, miss_1559, full_day_missing, spreads, gaps = [], [], [], [], []
    for d in dates:
        a, b = ny_ns(d, "09:30"), ny_ns(d, "11:05")
        i, j = mk.idx(a), mk.idx(b)
        if j - i != (b - a) // NS_PER_MIN:
            miss_win.append((d.isoformat(), int(j - i)))
        if i == j:
            full_day_missing.append(d.isoformat())
            continue
        c = mk.idx(ny_ns(d, "16:00")) - 1
        if c < 0 or int(mk.ts[c]) != ny_ns(d, "15:59"):
            miss_1559.append(d.isoformat())
        w0 = mk.idx(ny_ns(d, "10:00"))
        spreads.append(mk.ask["c"][w0:j] - mk.bid["c"][w0:j])
        if j - i > 1:
            jump = np.abs(mk.mid["o"][i + 1 : j] - mk.mid["c"][i : j - 1])
            k = int(np.argmax(jump))
            gaps.append((float(jump[k]), str(t[i + 1 + k])))
    sp = np.concatenate(spreads) if spreads else np.array([np.nan])
    rep["xnys_dates"] = len(dates)
    rep["dates_missing_m1_0930_1105"] = len(miss_win)
    rep["dates_missing_m1_examples"] = miss_win[:15]
    rep["dates_no_data_at_all"] = full_day_missing
    rep["dates_missing_1559_bar"] = len(miss_1559)
    rep["dates_missing_1559_examples"] = miss_1559[:10]
    rep["spread_10_1105"] = {
        "median": float(np.median(sp)),
        "p95": float(np.percentile(sp, 95)),
        "p99": float(np.percentile(sp, 99)),
        "max": float(sp.max()),
        "zero_share": float((sp == 0).mean()),
    }
    rep["largest_minute_jumps_0930_1105"] = sorted(gaps, reverse=True)[:5]
    dset = {pd.Timestamp(d) for d in dates}
    di = set(mk.daily.index[(mk.daily.index >= DEV_FIRST) & (mk.daily.index <= DEV_LAST)])
    rep["xnys_dates_without_daily_session"] = sorted(str(x.date()) for x in dset - di)
    rep["daily_sessions_not_xnys"] = len(rep["r29_non_xnys_sessions"])
    rep["dates_missing_1559_not_early_close"] = sorted(
        set(miss_1559) - set(rep["r28_early_close_dates"])
    )
    asia = set(mk.asia.index)
    rep["asia_range_available_share"] = float(np.mean([pd.Timestamp(d) in asia for d in dates]))
    # weekly reopen bar present (Sunday 17:00-19:00 NY) for NWOG
    mondays = sorted({d - dt.timedelta(days=d.weekday()) for d in dates})
    have = 0
    for m in mondays:
        s = m - dt.timedelta(days=1)
        i = mk.idx(ny_ns(s, "17:00"))
        have += int(i < len(mk.ts) and int(mk.ts[i]) < ny_ns(s, "19:00"))
    rep["weeks_with_sunday_reopen_bar_share"] = have / len(mondays)
    return rep, mk


def sync(mks: dict[str, Market], dates: list[dt.date]) -> dict[str, float]:
    out = {}
    for a, b in (("NAS100", "SPX"), ("SPX", "NAS100"), ("US30", "SPX")):
        ca, cb = mks[a].c5, mks[b].c5
        n = same = 0
        for d in dates:
            w0, w1 = ny_ns(d, "10:00"), ny_ns(d, "11:00")
            sa = set(ca.start[(ca.start >= w0) & (ca.end <= w1)])
            sb = set(cb.start[(cb.start >= w0) & (cb.end <= w1)])
            n += len(sa)
            same += len(sa & sb)
        out[f"{a}->{b}"] = same / n if n else float("nan")
    return out


def final_exam_availability() -> dict[str, object]:
    """Checks only whether 2012-2014 M1 partitions exist on disk; reads no file contents."""
    res = {}
    for name in INSTRUMENTS:
        years = sorted(
            {
                int(p.name.split("=")[1])
                for f in source_files(name)
                for p in f.parents
                if p.name.startswith("year=")
            }
        )
        res[name] = {
            "years_on_disk": years,
            "has_2012_2014": any(y in (2012, 2013, 2014) for y in years),
        }
    return res


def to_md(reps: dict[str, dict], syn: dict, fx: dict) -> str:
    lines = [
        "# Cycle 21 data-integrity audit (development data, no strategy execution)",
        "",
        f"Range audited: XNYS dates {DEV_FIRST} -> {DEV_LAST}; context data from 2017-11-01.",
        "",
    ]
    keys = [
        "symbol",
        "files",
        "rows",
        "validate_m1",
        "duplicate_ts",
        "nan_prices",
        "non_positive_prices",
        "crossed_o",
        "crossed_h",
        "crossed_l",
        "crossed_c",
        "inconsistent_bid_ohlc",
        "inconsistent_ask_ohlc",
        "saturday_bars",
        "sunday_before_17_bars",
        "crossed_bar_ny_dates",
        "crossed_bars_in_0930_1600",
        "window_0930_1105_bars",
        "window_bars_identical_to_previous",
        "first_bar_ny",
        "last_bar_ny",
        "xnys_dates",
        "dates_missing_m1_0930_1105",
        "dates_missing_1559_bar",
        "dates_missing_1559_not_early_close",
        "r27_excluded_sessions",
        "r31_frozen_side_bars",
        "r30_repeated_bars_total",
        "daily_sessions_not_xnys",
        "asia_range_available_share",
        "weeks_with_sunday_reopen_bar_share",
    ]
    lines += ["| check | " + " | ".join(reps) + " |", "|---|" + "---|" * len(reps)]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(str(r.get(k, "")) for r in reps.values()) + " |")
    lines.append("")
    for n, r in reps.items():
        lines += [f"## {n}", ""]
        for k in (
            "spread_10_1105",
            "dates_missing_m1_examples",
            "dates_no_data_at_all",
            "dates_missing_1559_examples",
            "r27_crossed_bars_by_session",
            "r28_early_close_dates",
            "r29_non_xnys_sessions",
            "xnys_dates_without_daily_session",
            "largest_minute_jumps_0930_1105",
            "rows_per_year",
        ):
            lines.append(f"- **{k}**: `{r.get(k)}`")
        lines.append("")
    lines += [
        "## SMT 5-minute timestamp synchronization (10:00-11:00, share of primary candles matched)",
        "",
        f"`{syn}`",
        "",
    ]
    lines += ["## Final exam (2012-2014) M1 availability (paths only, no reads)", "", f"`{fx}`", ""]
    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dates = xnys_dates(DEV_FIRST, DEV_LAST)
    reps, mks = {}, {}
    for name in INSTRUMENTS:
        reps[name], mks[name] = audit(name, dates)
        print(f"[c21-audit] {name} done", flush=True)
    ok = {k: v for k, v in mks.items() if v is not None}
    syn = sync(ok, dates) if len(ok) == len(mks) else {"skipped": "validation failure"}
    fx = final_exam_availability()
    (OUT / "data_audit.json").write_text(
        json.dumps({"instruments": reps, "smt_sync": syn, "final_exam": fx}, indent=2, default=str),
        "utf-8",
    )
    (OUT / "data_audit.md").write_text(to_md(reps, syn, fx), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
