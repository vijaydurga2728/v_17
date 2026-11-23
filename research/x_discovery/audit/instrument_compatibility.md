# Instrument Compatibility Matrix

**Date:** 2026-11-14
**Verified against:** `data/` tree and `C:\Users\Vijayakumar R\Documents\*.csv` on 2026-11-14.

## 1. What data exists (verified)

All price data is **Dukascopy CFD bid/ask**. Volume columns (`bid_volume`, `ask_volume`) are Dukascopy quote/tick volume, **not exchange volume**.

| Intended | Dukascopy symbol | Raw M1 CSV (Documents) | Ingested in repo |
|---|---|---|---|
| EURUSD | EURUSD | 2010-01 → 2026-10-18 | D1 2010–2026; M1 parquet; H1 |
| GBPUSD | GBPUSD | 2014-01 → 2026-10-18 | D1 2014–2026; M1 parquet; H1 |
| USDJPY | USDJPY | 2015-01 → 2026-10-24 | D1; M1 paired; M5 |
| USDCHF | USDCHF | 2015-01 → 2026-10-24 | D1 only |
| AUDUSD | AUDUSD | 2015-01 → 2026-10-24 | D1; M1 paired; M5 |
| USDCAD | USDCAD | 2010-01 → 2026-10-24 | D1 2010–2026 |
| NAS100 | USATECHIDXUSD | 2015-01 → 2026-11-10 | D1; M1 parquet; H1 |
| US500 | USA500IDXUSD | 2015-01 → 2026-10-14 | M1 paired; M5 (no D1 cache yet) |
| US30 | USA30IDXUSD | 2015-01 → 2026-10-14 (+ ticks 2014→) | **Not ingested** |

Also present but outside the intended universe: NZDUSD, EURGBP (ingested D1), BTCUSD, XAUUSD 2010–2014 (raw only).

**Important data properties:**
- Index CFD D1 bars are built from the ~23 h CFD session (2020 NAS100 D1 has 312 rows, i.e. Sunday bars included). They are **not** cash-session (09:30–16:00 ET) bars. Any rule defined on cash open/high/low/close (IBS, NR7, Connors RSI2 on SPY close, 80% rule, noise area, MIM) must be rebuilt from M1 restricted to the cash session.
- Index CFD prices track the cash index/futures blend chosen by Dukascopy. They are not SPY, QQQ, ES or NQ. Dividends are not in the price (SPY/QQQ total-return studies include them).

## 2. Broker symbols (partly verified)

| Intended | IC Markets demo (used by RSI2 demo) | FTMO |
|---|---|---|
| NAS100 | `USTEC` (verified in demo memory + `scripts/demo_poll_mt5.py`) | **Not verified this session** |
| US500 | Not verified | Not verified |
| US30 | Not verified | Not verified |
| FX majors | Standard names, not re-verified | Not verified |

**Action needed:** query `mt5.symbols_get()` on the IC Markets demo and read FTMO's current symbol list before any spec freezes. I did not do this, because it touches the running demo terminal.

## 3. Candidate × instrument matrix

✓ = data on disk supports the rule as written (after cash-session rebuild where noted). ~ = only a proxy test is possible. ✗ = data missing.

| # | Candidate | Native instrument | Data the rule needs | FX majors | NAS100 | US500 | US30 | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | ORB stocks-in-play | 7,000 US stocks, 5-min, exchange volume | Stock universe + exchange volume for relative-volume ranking | ✗ | ~ (index ORB only; no stock selection) | ~ | ~ | **Needs data** for the real strategy. Index proxy is a different strategy and already net zero (Krueger). |
| 2 | Noise Area | SPY 1-min + volume (VWAP) | Cash open, minute-by-minute 14-day move profile, VWAP | ✗ (no defined open; theory is equity flow) | ✓ M1 | ✓ M1 | ✓ after ingest | ~ VWAP uses CFD tick volume, not exchange volume; `compute_session_vwap` already has a typical-price fallback. |
| 3 | EWMAC | Diversified futures, daily | D1 closes, vol estimate | ✓ D1 (6 majors) | ✓ D1 | ✓ after D1 build | ✓ after ingest | Usable. 9 instruments, USD-correlated; far less diversification than Carver's 30–100 markets. Swap/financing costs must be modelled. |
| 4 | GEM | US equity, ex-US equity, bonds (monthly) | Total-return series for 3 asset classes | ✗ | ~ | ~ | ~ | **Incompatible.** No ex-US equity index, no bonds; user excluded bonds. |
| 5 | IBS QQQ | QQQ daily | Cash-session OHLC | — | ✓ after cash rebuild | ✓ | ✓ | Usable but overlaps RSI2-NAS100. |
| 6 | NR7 | SPY daily (implied) | Cash-session ranges | — | ✓ | ✓ | ✓ | Usable but rules ambiguous. |
| 7 | MIM | SPY 30-min returns | Prev cash close, 10:00 ET price, 15:30–16:00 ET prices | ✗ | ✓ M1 | ✓ M1 | ✓ after ingest | **Directly compatible.** Only needs prices at four timestamps per day. |
| 8 | RSI2 ES/NQ | ES/NQ futures daily | Futures daily OHLC | — | ✓ (already live) | ✓ | ✓ | Already covered by the demo strategy. |
| 9 | Silver Bullet | ES/NQ 1-min | Undefined "Dealing Range" | — | — | — | — | Untestable. |
| 10 | 80% rule | ES futures, TPO/volume profile, footprint | Exchange volume / order flow | ✗ | ~ TPO from M1 time only | ~ | ~ | Footprint step needs order flow we do not have. |
| 11 | IB iFVG | Futures, proprietary indicator | Closed indicator | ✗ | ✗ | ✗ | ✗ | Untestable. |

## 4. No silent substitutions

Any test run on our data is a test of **"the rule on Dukascopy index CFDs with retail spread"**, not a replication of the SPY/QQQ/ES/NQ paper result. A spec must name the substitution, for example: "SPY → USA500IDXUSD cash-session M1, mid price, Dukascopy bid/ask spread charged, no dividends."
