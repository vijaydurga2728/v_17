# Code Inventory vs Spec Requirements

**Date:** 2026-11-03

**Reference:** `docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md` section 15


| Requirement | Spec Phase | File | Exists | LOC | Status |
|---|---|---|---|---|---|
| Dukascopy paired bid/ask ingest | P2 | `src/v17/data/dukascopy_csv.py` | yes | 138 | present |
| Parquet store with partition tag | P2 | `src/v17/data/parquet_store.py` | yes | 51 | present |
| Partition guard (holdout seal) | P2 | `src/v17/data/partition_guard.py` | no | 0 | missing |
| Finnhub calendar backfill | P1 | `src/v17/data/calendar/__init__.py` | yes | 0 | stub |
| D1 bias calculator (SB-A1) | P5 | `src/v17/structure/bias.py` | yes | 101 | present |
| FVG detector (causal) | P5 | `src/v17/structure/fvg.py` | yes | 72 | present |
| MSS detector (close-based) | P5 | `src/v17/structure/mss.py` | yes | 47 | present |
| Session boundaries NY/London | P5 | `src/v17/structure/session.py` | no | 0 | missing |
| Silver Bullet FSM | P5 | `src/v17/setups/silver_bullet_fsm.py` | no | 0 | missing |
| Instrument spec (pip sizes) | P5 | `src/v17/common/instrument_spec.py` | no | 0 | missing |
| Cost model (bid/ask + commission) | P2+P5 | `src/v17/backtest/cost.py` | yes | 187 | present |
| Fill model (limit, market) | P5 | `src/v17/backtest/fills.py` | yes | 76 | present |
| Backtest event loop | P5 | `src/v17/backtest/loop.py` | yes | 281 | present |
| Walk-forward harness | P7 | `src/v17/backtest/walkforward.py` | yes | 36 | present |
| MCPT harness | P8 | `src/v17/validation/mcpt.py` | yes | 155 | present |
| Validation gate | P10 | `src/v17/validation/gate.py` | yes | 55 | present |
| Validation thresholds | P10 | `src/v17/validation/thresholds.py` | yes | 14 | present |
| Risk engine (position sizing) | P5 | `src/v17/risk/engine.py` | yes | 168 | present |
| Risk rules (circuit breakers) | P5 | `src/v17/risk/risk_rules.py` | yes | 16 | present |
| MT5 reconciliation | future-live | `src/v17/live/reconcile.py` | no | 0 | missing |

