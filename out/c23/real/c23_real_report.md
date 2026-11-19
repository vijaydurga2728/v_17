# Cycle 23 real-data run (dev 2018-2024, Model A, SMT off)

Git `f60ec5c`, config `a25af5711afb32d4`, holdout 2012-2014 not loaded.

## Step 1: event parity — **MATCH**

Details: `event_parity_real.md`.

## Step 3: R26 performance gates (unchanged)

| instrument | trades | net PF | mean R | doubled-cost PF | luck p | max DD (R) | R^2 | gates | verdict |
|---|---|---|---|---|---|---|---|---|---|
| NAS100 | 0 | nan | +nan | nan | not run | nan | nan | failed: PF>=1.30, trades>=100, meanR>0, 2xcostPF>=1.10, luck p<=0.0167 | **FAIL** |
| SPX | 0 | nan | +nan | nan | not run | nan | nan | failed: PF>=1.30, trades>=100, meanR>0, 2xcostPF>=1.10, luck p<=0.0167 | **FAIL** |
| US30 | 0 | nan | +nan | nan | not run | nan | nan | failed: PF>=1.30, trades>=100, meanR>0, 2xcostPF>=1.10, luck p<=0.0167 | **FAIL** |

- NAS100: doubled-cost run not run: trade-count gate already failed

- SPX: doubled-cost run not run: trade-count gate already failed

- US30: doubled-cost run not run: trade-count gate already failed
