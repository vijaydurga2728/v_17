# Audit 1 — Rulebook vs Transcript

**Date:** 2026-11-03
**Reference rulebook:** research/ict/ICT_STRATEGY_RULEBOOK.md
**Transcript root:** C:/personal/ICT transcript/

| Rule ID | Classification | Cited Transcript | Timestamp Range | Verdict | Notes |
| :-- | :-- | :-- | :-- | :-- | :-- |
| P-01 | SOURCE_CONFIRMED | `ict2022/019 - 2022 ICT Mentorship Episode 19.en.vtt` | [01:39:10]–[01:40:12] | MINOR_PARAPHRASE | Core meaning confirmed. Rulebook omits "you want to be a buyer" from "below the opening price you want to be a buyer at midnight by itself." Trap/snare quote confirmed with minor word reorder. |
| P-01 | SOURCE_CONFIRMED | `chart_content/001 - ICT Charter Price Action Model 1.en.vtt` | [00:06:59]–[00:07:30] | MISMATCH | Range contains rejection-block/turtle-suit reversal discussion. No mention of "midnight candle," "Eastern Standard Time," or "when we're bullish we want to be buying at that price or below it." |
| P-01 | SOURCE_CONFIRMED | `chart_content/001 - ICT Charter Price Action Model 1.en.vtt` | [00:22:36]–[00:23:09] | MISMATCH | Range contains daily liquidity pool protocol / "do not force another trade if you're stopped out." No mention of midnight anchor or Eastern Standard Time. |
| P-02 | SOURCE_CONFIRMED | `ict2022/009 - 2022 ICT Mentorship Episode 9.en.vtt` | [00:02:40]–[00:03:41] | MISMATCH | Transcript reads: "power three which is **accumulation, distribution, and manipulation**" (A-D-M order). Rulebook quotes: "accumulation, manipulation, and distribution" (A-M-D order). The remainder of the quote (Judas swing false move in London/NY) is confirmed. Order mismatch is material for the AMD acronym used throughout the spec. |
| P-03 | SOURCE_CONFIRMED | `market_structure/047 - Pattern Recognition - Breakers & Market Structure.en.vtt` | [00:12:15]–[00:15:30] | MISSING_CITATION | File ends at 00:08:01 (301 cues). Cited range is entirely beyond end of file. Keywords "break of structure," "market structure shift," "fair value gap," "body must close," and "violently" are absent from the entire file. |
| P-04 | SOURCE_CONFIRMED | `ict2022/002 - 2022 ICT Mentorship Episode 2.en.vtt` | [00:14:10]–[00:18:22] | MISMATCH | Range contains draw-on-liquidity / paperclip analogy. The quoted FVG definition ("3-candle pattern where candle 2 has a large range," "unfilled area where only one side of the market was delivered," "Consequent Encroachment") does not appear at this timestamp or anywhere in Ep 2. Keywords "consequent encroachment," "three-candle pattern," and "unfilled area" are absent from the entire Ep 2 file. |
| JS-02 | SOURCE_INTERPRETATION | `market_structure/014 - ICT Forex Lesson - Keys To Daily Bias In The Forex Market.en.vtt` | [00:08:45]–[00:14:20] | MISMATCH | Cited range covers London Close killzone timing discussion, not the quoted "draw on liquidity" content. The phrase "draw on liquidity" exists in MS14 but at ~00:22:41. "Unmitigated daily fair value gap," "buy-side," and "resting… liquidity" do not appear anywhere in the file. The quoted passage appears to be a paraphrase constructed from multiple lessons, not a direct quote from this file at this timestamp. |
| JS-03 | SOURCE_CONFIRMED | `chart_content/001 - ICT Charter Price Action Model 1.en.vtt` | [00:40:16]–[00:43:10] | MISSING_CITATION | File ends at 00:27:27. Cited range is beyond end of file. Keywords "Asian range," "20 to 30 pips," "spring," and "manipulation" are absent from the entire Charter Model 1 file. |
| JS-07 | SOURCE_CONFIRMED | `chart_content/001 - ICT Charter Price Action Model 1.en.vtt` | (no timestamp cited) | MISSING_CITATION | Compliance matrix cites "Charter Model 1 Asian Target" with no timestamp. Keyword "asian" is absent from the entire Charter Model 1 file. Asian High / Asian Low as take-profit targets not supported by this file. |
| SB-01 | SOURCE_CONFIRMED | "2023 Silver Bullet Lecture" | (no file/timestamp cited) | MISSING_CITATION | No Silver Bullet transcript file exists in the corpus (searched ict2022/, chart_content/, market_structure/, and root). Source file cannot be verified. |
| SB-02 | SOURCE_CONFIRMED | "2023 Silver Bullet Lecture" | (no file/timestamp cited) | MISSING_CITATION | Same as SB-01: no transcript file found. |
| SB-04 | SOURCE_CONFIRMED | "2023 Silver Bullet Lecture" | (no file/timestamp cited) | MISSING_CITATION | Same as SB-01: no transcript file found. |
| SB-05 | SOURCE_CONFIRMED | "2023 Silver Bullet Lecture" | (no file/timestamp cited) | MISSING_CITATION | Same as SB-01: no transcript file found. |

---

## Summary

- CONFIRMED: 0
- MINOR_PARAPHRASE: 1 (P-01 Ep19 citation)
- MISMATCH: 5 (P-01 both Charter citations, P-02, P-03 content mismatch at wrong file extent, P-04, JS-02)
- MISSING_CITATION: 7 (P-03 beyond file, JS-03, JS-07, SB-01, SB-02, SB-04, SB-05)
- MISCLASSIFIED: 0

**Total rules audited:** 13 citation-instances across 11 rules  
(P-01 has two Charter citations checked independently; JS-01, JS-04, JS-05, JS-06, SB-03 are ENGINEERING_CONSTRAINT or RESEARCH_HYPOTHESIS and excluded per task scope)

---

## Rules requiring spec amendment

The following rule parameters are directly affected by verdict findings in section 5 of the spec:

1. **P-02** (AMD order): The AMD acronym is used throughout the spec as "Accumulation → Manipulation → Distribution." The transcript at the cited range states A-D-M order. If the spec's AMD sequencing is load-bearing (it is — the Judas Swing manipulation phase is step 2), the acronym order must be corrected or a second corroborating citation must be found that uses A-M-D order. Note: Ep19 (in P-01 range) does say "accumulation manipulation distribution" in that order at 01:39:58, which supports A-M-D — but that citation belongs to P-01, not P-02.

2. **P-03** (MSS close-confirmation rule): The "candle body must close beyond the swing high or low" rule (spec Rule P-03 §2) has no verifiable transcript backing. This rule gates the MSS trigger across all three strategy engines. Until a valid citation is located, it should be reclassified `SOURCE_INTERPRETATION`.

3. **P-04** (FVG / CE definition): The Consequent Encroachment midpoint definition and the 3-candle structural definition have no verifiable transcript backing in Ep 2. These underpin every FVG entry in SB-04 and JS entry logic. Until a valid citation is located, P-04 should be reclassified `SOURCE_INTERPRETATION`.

4. **JS-03** (Asian Range 30-pip contraction gate): The 30-pip threshold cited to Charter Model 1 at [00:40:16] cannot be verified — the file ends at 00:27:27. This threshold directly controls the JS contraction gate parameter. Until verified, it should be reclassified `RESEARCH_HYPOTHESIS`.

5. **SB-01** (Silver Bullet window times): 03:00–04:00, 10:00–11:00, 14:00–15:00 NY have no verifiable transcript backing. These are spec section 5 operational time boundaries for all three SB engines.

---

## Proposed corrections

### P-01 (Charter citations — MISMATCH)
**Proposed correction:** Remove or replace the two Charter Model 1 citations (`[00:06:59]–[00:07:30]` and `[00:22:36]–[00:23:09]`). Neither range contains any content related to the midnight anchor or buying below midnight. A valid supporting citation for the Charter Model 1 midnight claim requires a new transcript search. The Ep19 citation alone is sufficient to maintain SOURCE_CONFIRMED status for the core rule.

### P-02 (AMD order — MISMATCH)
**Proposed correction:** Change the rulebook quote to reflect the transcript accurately:
> "I want to talk a little bit about power three which is accumulation, **distribution**, and manipulation"

And update the Algorithmic Sequence label order to A-D-M, or add a footnote acknowledging the transcript uses A-D-M at this citation while ICT uses A-M-D in later content (e.g., Ep19 at 01:39:58 uses A-M-D order). The spec's functional description of Manipulation as the Judas Swing (step 2) is not invalidated — only the cited evidence for the acronym ordering is.

### P-03 (MISSING_CITATION — wrong file / beyond file length)
**Proposed correction:** Reclassify to `SOURCE_INTERPRETATION`. The cited file (MS47) ends at 00:08:01; the cited range [00:12:15]–[00:15:30] does not exist. The "close beyond swing high/low" confirmation rule is a reasonable algorithmic encoding of ICT's close-confirmation teaching but cannot be attributed to this specific citation. A replacement citation search across market_structure/ and ict2022/ files is required before restoring SOURCE_CONFIRMED.

### P-04 (MISMATCH — content not in cited range or file)
**Proposed correction:** Reclassify to `SOURCE_INTERPRETATION`. The cited range in Ep2 contains draw-on-liquidity content. The FVG 3-candle definition and "Consequent Encroachment" terminology are not present in Ep2. A replacement citation (likely from a later 2022 mentorship episode or a dedicated FVG lesson) is required.

### JS-02 (MISMATCH — wrong timestamp range)
**Proposed correction:** Update timestamp to approximately [00:22:41] in MS14, where "draw on liquidity" content exists. Remove "unmitigated daily fair value gap" and "buy-side/sell-side liquidity" from the direct quote — these phrases are not present in MS14. The EMA20 filter (JS-02 §2) has no citation anywhere in the reviewed corpus and should be reclassified `RESEARCH_HYPOTHESIS`.

### JS-03 (MISSING_CITATION — beyond file length)
**Proposed correction:** Reclassify to `RESEARCH_HYPOTHESIS`. Charter Model 1 ends at 00:27:27; the 30-pip contraction threshold at [00:40:16] cannot be verified. The 30-pip threshold is a quantitative interpretation, not a directly stated value in the available transcript.

### JS-07 (MISSING_CITATION — no Asian content in cited file)
**Proposed correction:** Remove Charter Model 1 as citation source. "Asian" does not appear in Charter Model 1. A replacement citation within ict2022/ or a different Charter file is required. Until found, reclassify to `SOURCE_INTERPRETATION`.

### SB-01, SB-02, SB-04, SB-05 (MISSING_CITATION — transcript file absent)
**Proposed correction:** Reclassify all four as `RESEARCH_HYPOTHESIS` pending location of the "2023 Silver Bullet Lecture" transcript. If the file exists outside the corpus paths searched, its path must be added to the transcript root and re-audited. The Silver Bullet window times (SB-01), liquidity pool rules (SB-02), FVG-only entry (SB-04), and target architecture (SB-05) are currently unverified against any primary source in this corpus.
