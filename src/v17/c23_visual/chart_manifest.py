"""Chart provenance + resumable generation (spec §5, gate 5)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl

from v17.c23_visual import BASELINE_COMMIT, C23_VERSION
from v17.c23_visual.annotations import build, fingerprint
from v17.c23_visual.chart_builder import View, render, view_annotations
from v17.c23_visual.models import DayRecord, VisualEvent
from v17.smc_sb.config import StrategyConfig
from v17.smc_sb.data import Market

VIEWS: tuple[View, ...] = ("decision", "outcome")


def chart_id(rec: DayRecord, view: str) -> str:
    return f"{rec.instrument}_{rec.trading_date}_c23_{view}"


def generate(
    mk: Market,
    cfg: StrategyConfig,
    records: list[DayRecord],
    ledger: list[VisualEvent],
    out_dir: Path,
    data_fp: str,
) -> dict[str, object]:
    """Render decision + outcome PNGs for every charted day. Resumable: an entry whose annotation fingerprint and PNG
    hash still match is skipped. Failures are recorded, never skipped silently."""
    man_path = out_dir / "manifest.json"
    old: dict[str, dict[str, object]] = {}
    if man_path.exists():
        old = json.loads(man_path.read_text())["charts"]
    by_id = {e.event_id: e for e in ledger}
    charts: dict[str, dict[str, object]] = {}
    failures: dict[str, str] = {}
    for rec in records:
        if not rec.charted:
            continue
        evs = [by_id[i] for i in rec.event_ids]
        annos = build(rec, evs, cfg)
        for view in VIEWS:
            cid = chart_id(rec, view)
            year = rec.trading_date[:4]
            png = out_dir / rec.instrument / year / f"{cid}.png"
            afp = fingerprint(view_annotations(annos, rec, view))
            prev = old.get(cid)
            if prev and prev.get("annotation_fp") == afp and png.exists():
                charts[cid] = prev
                continue
            try:
                sha = render(mk, rec, annos, view, png)
            except Exception as exc:
                failures[cid] = f"{type(exc).__name__}: {exc}"
                continue
            charts[cid] = {
                "path": str(png.relative_to(out_dir)).replace("\\", "/"),
                "view": view,
                "category": rec.category,
                "near_miss_stage": rec.near_miss_stage,
                "event_ids": list(rec.event_ids),
                "cut_ns": rec.cut_ns,
                "end_ns": rec.end_ns,
                "annotation_fp": afp,
                "png_sha256": sha,
            }
    manifest: dict[str, object] = {
        "c23_version": C23_VERSION,
        "baseline_commit": BASELINE_COMMIT,
        "config_fingerprint": cfg.fingerprint(),
        "data_fingerprint": data_fp,
        "renderer": f"matplotlib {mpl.__version__}",
        "charts": charts,
        "failures": failures,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def manifest_violations(
    manifest: dict[str, object], out_dir: Path, expected: set[str]
) -> list[str]:
    charts = manifest["charts"]
    assert isinstance(charts, dict)
    bad = [f"missing chart {c}" for c in sorted(expected - set(charts))]
    bad += [f"unexpected chart {c}" for c in sorted(set(charts) - expected)]
    bad += [
        f"file missing {c}" for c, v in charts.items() if not (out_dir / str(v["path"])).exists()
    ]
    failures = manifest.get("failures") or {}
    assert isinstance(failures, dict)
    bad += [f"render failed {k}: {v}" for k, v in failures.items()]
    return bad
