# ICT Strategy Rulebook: Transcript-Backed Mechanical Doctrine

**Document ID:** `research/ict/ICT_STRATEGY_RULEBOOK.md`  
**Author:** Quantitative Research & ICT Methodology Team  
**Date:** 2026-11-03  
**Status:** FROZEN RESEARCH SPECIFICATION  
**Sources:** ICT 2022 Mentorship (Episodes 1–41), Charter Content Models 1–12, OTE Pattern Recognition Series (Vols 1–20), ICT Market Structure Series (Lessons 1–47).

---

## 1. Classification System

Every trading rule, filter, and threshold in this rulebook is explicitly tagged with one of five rigorous classifications:

| Classification | Definition & Operational Standard |
| :--- | :--- |
| **`SOURCE_CONFIRMED`** | Directly stated by Michael J. Huddleston in video transcripts with specific episode/timestamp citations. Immutable without new transcript evidence. |
| **`SOURCE_INTERPRETATION`** | A reasonable mathematical/algorithmic translation of a descriptive or visual ICT concept where no exact equation was provided. |
| **`RESEARCH_HYPOTHESIS`** | A heuristic or parameter introduced for statistical testing that requires empirical walk-forward proof. |
| **`ENGINEERING_CONSTRAINT`** | An operational requirement imposed by broker APIs, execution latency, discrete tick sizes, or memory safety. |
| **`NOT_SUPPORTED`** | A common retail or internet trading assumption that is explicitly unsupported or contradicted by primary ICT sources. |

---

## 2. Core Methodological Primitives

### Rule P-01: True Daily Open Anchor (New York Midnight)
- **Classification:** `SOURCE_CONFIRMED`
- **Transcript Citation:** 
  - *2022 Mentorship, Episode 19* (`[01:39:10] - [01:40:12]`):  
    > "Below the opening price at midnight by itself that's always the basis of what I'm trying to do each day... Each move lower is the trap, the snare that catches traders thinking it's going down."
  - Classification remains SOURCE_CONFIRMED based on Episode 19 only. Audit 1 (2026-11-03) found both Charter Model 1 citations do not contain this content; they have been removed. Minor paraphrase accepted.
- **Algorithmic Rule:**  
  1. The benchmark anchor for the daily cycle is the opening price of the 00:00:00 candle in timezone `America/New_York` ($P_{\text{NY\_Midnight}}$).
  2. For a BULLISH daily bias: High-probability long setups require price to trade *strictly below* $P_{\text{NY\_Midnight}}$.
  3. For a BEARISH daily bias: High-probability short setups require price to trade *strictly above* $P_{\text{NY\_Midnight}}$.
- **Invalidation:** An entry taken above $P_{\text{NY\_Midnight}}$ on a long trade (or below on a short) is an invalid Judas setup.

### Rule P-02: Power of Three (AMD — Accumulation, Manipulation, Distribution)
- **Classification:** `SOURCE_CONFIRMED`
- **Transcript Citation:**  
  - *2022 Mentorship, Episode 9* (`[00:02:40] - [00:03:41]`):  
    > "I want to talk a little bit about power three which is accumulation, distribution, and manipulation... if I'm bullish I'm expecting the opening price to be near the low of the day or session, then it trades lower making some important low, rallies, and closes near the high... The Judas swing is the false move typically in London and New York session."
  - Note: Ep9 cited quote uses A-D-M acronym order. The spec's A-M-D usage of the acronym is supported separately by Episode 19 at ~[01:39:58] which uses A-M-D. The Judas swing (manipulation) as the false-move step is confirmed in the subsequent sentences of the Ep9 citation range. Classification remains SOURCE_CONFIRMED.
- **Algorithmic Sequence:**
  1. **Accumulation:** Consolidation phase during the Asian session where liquidity accumulates above/below the range.
  2. **Manipulation (Judas Swing):** Aggressive false run opposing the HTF bias, piercing session/liquidity levels to trigger stops and engineer liquidity for institutional orders.
  3. **Distribution:** True directional trend expansion delivering toward opposing liquidity pools.

### Rule P-03: Market Structure Shift (MSS) vs. Break of Structure (BOS)
- **Classification:** `SOURCE_INTERPRETATION`
- **Transcript Citation:** None. Audit 1 (2026-11-03) found the cited range [00:12:15]-[00:15:30] does not exist in Market Structure Lesson 47 (file ends at 00:08:01). The close-based MSS confirmation rule is retained as a reasonable algorithmic interpretation of ICT's teaching, but a confirming transcript citation has not been located.
- **Algorithmic Rule:**
  1. Swing points are defined strictly causally: A 3-bar swing high requires $H_{t-1} \le H_t$ and $H_{t+1} < H_t$. Confirmation occurs only after bar $t+1$ closes.
  2. For a Bullish MSS: Price must print a bar whose **Close** $> \text{Swing High}$ on the execution timeframe (M1 or M5). A mere wick breach is a liquidity sweep, NOT an MSS.
  3. For a Bearish MSS: Price must print a bar whose **Close** $< \text{Swing Low}$.

### Rule P-04: Fair Value Gap (FVG) Definition & Consequent Encroachment
- **Classification:** `SOURCE_INTERPRETATION`
- **Transcript Citation:** None in cited location. Audit 1 (2026-11-03) found that Ep2 range [00:14:10]-[00:18:22] contains draw-on-liquidity content, not FVG/CE definition. The 3-candle FVG definition and Consequent Encroachment midpoint are retained as the standard ICT algorithmic encoding, but no confirming transcript citation has been located in the available corpus.
- **Algorithmic Rule:**
  - Bullish FVG at bar $i$: $L_{i} > H_{i-2}$. Imbalance range: $[H_{i-2}, L_{i}]$.
  - Bearish FVG at bar $i$: $H_{i} < L_{i-2}$. Imbalance range: $[H_{i}, L_{i-2}]$.
  - Consequent Encroachment (CE): $\text{CE} = (\text{Top} + \text{Bottom}) / 2$.
  - Mitigation State: A gap is partially mitigated when price touches the proximal edge; it is fully mitigated when price crosses the distal edge ($H_{i-2}$ for bullish, $L_{i-2}$ for bearish).

---

## 3. Model A: ICT Judas Swing Strategy Rulebook

### Rule JS-01: Instrument Eligibility
- **Classification:** `ENGINEERING_CONSTRAINT` (Derived from empirical evidence & ICT London Killzone focus)
- **Rule:** Active exclusively on **`EURUSD`** and **`GBPUSD`**.
- **Rationale:** Indices (`USATECHIDXUSD`) are New York-centric instruments and do not exhibit authentic institutional Judas manipulation in the 07:00 London hour. `USDJPY` and `EURGBP` are excluded due to structural session mismatch and low ADR.

### Rule JS-02: Multi-Timeframe Daily Bias Framework
- **Classification:** `SOURCE_INTERPRETATION`
- **Transcript Citation:**  
  - *Market Structure Lesson 14 (Keys To Daily Bias In The Forex Market)* (`[00:08:45] - [00:14:20]`):  
    > "Daily bias is determined by asking: Where is the next draw on liquidity? Is price reaching for an unmitigated daily fair value gap or resting buy-side/sell-side liquidity on the daily chart?"
  - Note: Audit 1 (2026-11-03) found MS14 at [00:08:45]-[00:14:20] covers London Close killzone timing, not draw-on-liquidity. The "draw on liquidity" phrase appears in MS14 at ~00:22:41 (updated citation). The EMA20 filter (section 2 of this rule) has no transcript citation anywhere in the reviewed corpus and is classified RESEARCH_HYPOTHESIS. The daily-structure component remains SOURCE_INTERPRETATION.
- **Deterministic Algorithmic Translation:**
  1. High-Timeframe (D1) State:
     - Check Daily Market Structure: Trend of Daily Swings (Higher Highs/Higher Lows = Bullish; Lower Highs/Lower Lows = Bearish).
     - Daily Draw on Liquidity: Measure proximity to nearest unmitigated Daily FVG or Daily Old High/Low.
  2. Immediate Filter: Daily 20-period Exponential Moving Average (EMA20):
     - $\text{Close}_{\text{D1}} > \text{EMA20}_{\text{D1}} \implies \text{Bullish Alignment}$.
     - $\text{Close}_{\text{D1}} < \text{EMA20}_{\text{D1}} \implies \text{Bearish Alignment}$.
  3. Conflict & No-Bias Rule: If D1 swing structure opposes D1 EMA20, bias is `NONE`. Strategy transitions to `IDLE` and refuses all orders for that day.

### Rule JS-03: Asian Range Mechanics & Contraction Filter
- **Classification:** `RESEARCH_HYPOTHESIS`
- **Transcript Citation:** None confirmed. Audit 1 (2026-11-03) found Charter Model 1 ends at 00:27:27; the cited range [00:40:16]-[00:43:10] does not exist. The 30-pip Asian contraction threshold is a quantitative heuristic, not a directly stated value in the available transcripts.
- **Algorithmic Rule:**
  1. Time Boundaries: 20:00 to 00:00 `America/New_York` (evaluating bars prior to midnight).
  2. Asian Range High ($P_{\text{Asian\_High}}$) = $\max(H_t)$, Asian Range Low ($P_{\text{Asian\_Low}}$) = $\min(L_t)$ for $t \in [\text{20:00 NY}, \text{00:00 NY})$.
  3. Contraction Gate:
     $$\text{Asian Range Pips} = \frac{P_{\text{Asian\_High}} - P_{\text{Asian\_Low}}}{\text{pip\_size}} \le 30.0\text{ pips}$$
  4. Invalidation: If $\text{Asian Range Pips} > 30.0$, reject. The market has expanded prematurely.

### Rule JS-04: Disaggregated Session Timing Architecture
- **Classification:** `ENGINEERING_CONSTRAINT` (Resolving timing ambiguities)
- **Timezone:** `Europe/London` (DST-aware via standard tz database)
- **Time Boundaries:**
  - `session_start`: 07:00 London (Killzone open)
  - `manipulation_start`: 07:00 London
  - `primary_manipulation_end`: 08:30 London (Primary sweet-spot for false run)
  - `extended_manipulation_end`: 09:15 London (Latest permissible sweep detection)
  - `entry_cutoff`: 10:00 London (No new orders allowed after Killzone closes)
  - `pending_order_expiry`: 10:30 London (Unfilled limit orders cancelled)
  - `position_exit_time`: 16:00 London (London Close session exit; no overnight hold)

### Rule JS-05: Manipulation Sweep & Reclaim
- **Classification:** `SOURCE_INTERPRETATION` / `RESEARCH_HYPOTHESIS`
- **Algorithmic Rule:**
  1. Sweep Trigger:
     - For BUY: A 1m bar prints $L_t < P_{\text{Asian\_Low}}$ AND $L_t < P_{\text{NY\_Midnight}}$.
     - For SELL: A 1m bar prints $H_t > P_{\text{Asian\_High}}$ AND $H_t > P_{\text{NY\_Midnight}}$.
  2. Sweep Extreme ($P_{\text{Sweep\_Extreme}}$): The absolute minimum (for BUY) or maximum (for SELL) price reached during the manipulation leg.
  3. Reclaim Window: Price must close back inside the Asian Range within a maximum of **15 bars (M1)** or **3 bars (M5)** following the extreme wick. Failure to reclaim within 15 minutes invalidates the setup (classified as an authentic breakout run rather than an institutional trap).

### Rule JS-06: Judas Stop Loss & Execution Safety
- **Classification:** `ENGINEERING_CONSTRAINT`
- **Algorithmic Rule:**
  1. Theoretical Stop: Anchored 1 pip beyond $P_{\text{Sweep\_Extreme}}$:
     $$\text{SL}_{\text{theoretical}} = P_{\text{Sweep\_Extreme}} - (\text{pip\_size} \times 1.0) \quad (\text{for BUY})$$
  2. Broker Constraint Check:
     $$\text{Distance} = \frac{|P_{\text{entry}} - \text{SL}_{\text{theoretical}}|}{\text{pip\_size}}$$
     If $\text{Distance} < 2.0\text{ pips}$, widen SL to exactly $2.0\text{ pips}$ to satisfy broker freeze/stop-level rules.
  3. Pre-Trade Maximum Stop Cap: If $\text{Distance} > 15.0\text{ pips}$ for EURUSD/GBPUSD, reject. The stop is excessively wide for an intraday scalping model.

### Rule JS-07: Take Profit & Liquidity Target
- **Classification:** `SOURCE_INTERPRETATION`
- **Transcript Citation:** None in Charter Model 1 (keyword "asian" absent from entire file). Audit 1 (2026-11-03). The Asian-range high/low as take-profit targets is standard ICT practice but unverified in the available corpus.
- **Rule:**
  - For BUY: Primary Target = $P_{\text{Asian\_High}}$.
  - For SELL: Primary Target = $P_{\text{Asian\_Low}}$.
  - Minimum R:R Verification:
    $$R:R = \frac{|\text{Target} - P_{\text{entry}}|}{|P_{\text{entry}} - P_{\text{sl}}|}$$
    If $R:R < 1.5$, the setup is rejected.
  - Secondary Target: If opposing Asian extreme gives $R:R \ge 1.5$, target the Asian extreme. If Asian extreme is already tapped, target Previous Day High/Low (PDH/PDL).

---

## 4. Model B: ICT Silver Bullet Strategy Rulebook

### Rule SB-01: Independent Window Configuration
- **Classification:** `RESEARCH_HYPOTHESIS`
- **Transcript Citation:** None. Audit 1 (2026-11-03) found no Silver Bullet transcript file in the user's corpus. The parameters in this rule (window times, liquidity pool definitions, FVG entry mechanics, target selection) are widely-circulated ICT heuristics and are tested empirically under the frozen rulebook / zero-training / MCPT gate.
- **Timezone:** `America/New_York` (strictly enforced via tz database)
- **Strategy Engines:** Configured as three distinct operational profiles:
  1. `SilverBullet_London`: `03:00 – 04:00 NY` (08:00 – 09:00 London). Eligible symbols: `EURUSD`, `GBPUSD`.
  2. `SilverBullet_NY_AM`: `10:00 – 11:00 NY` (Post-equities open). Eligible symbols: `USATECHIDXUSD`, `EURUSD`, `GBPUSD`.
  3. `SilverBullet_NY_PM`: `14:00 – 15:00 NY` (Afternoon acceleration). Eligible symbols: `USATECHIDXUSD`.
- **Constraint:** Orders and signals may only be created inside the active 60-minute window. Pending orders are cancelled at Minute 59 (`XX:59:00 NY`).

### Rule SB-02: Eligible Liquidity Pools (No Asian Fallback)
- **Classification:** `RESEARCH_HYPOTHESIS`
- **Transcript Citation:** None. Audit 1 (2026-11-03) found no Silver Bullet transcript file in the user's corpus. The parameters in this rule (window times, liquidity pool definitions, FVG entry mechanics, target selection) are widely-circulated ICT heuristics and are tested empirically under the frozen rulebook / zero-training / MCPT gate.
- **Rule:** Price must sweep a prominent, locally relevant liquidity pool.
- **Eligible Liquidity Sources:**
  1. Session Extreme: The high/low established between 00:00 NY and the start of the window.
  2. Previous Hour High/Low: The high/low of the immediately preceding 1-hour candle.
  3. Prominent M15 Swing Point: An unmitigated swing high/low formed within the last **45 minutes**.
- **Prohibition (`NOT_SUPPORTED`):** Silver Bullet NEVER queries the previous day's Asian session extremes during the 10:00 AM or 14:00 PM New York windows. The legacy Asian-range fallback is permanently deleted.

### Rule SB-03: Measurable Displacement Criteria
- **Classification:** `RESEARCH_HYPOTHESIS` (Quantifying descriptive terminology)
- **Transcript Context:** ICT describes displacement as "energetic, long-bodied candles that show institutional intent."
- **Mathematical Specification:**
  A displacement event is valid if and only if:
  1. Candle Body Ratio: $\frac{|\text{Close} - \text{Open}|}{\text{High} - \text{Low}} \ge 0.65$ (at least 65% of the candle range is body, indicating zero indecision).
  2. Magnitude Check: Candle range $(\text{High} - \text{Low}) \ge 1.5 \times \text{ATR}_{14}(\text{M1})$.
  3. Imbalance Creation: The displacement candle MUST leave an unfilled Fair Value Gap (FVG) between Candle 1 and Candle 3.

### Rule SB-04: Fair Value Gap Entry Mechanics
- **Classification:** `RESEARCH_HYPOTHESIS`
- **Transcript Citation:** None. Audit 1 (2026-11-03) found no Silver Bullet transcript file in the user's corpus. The parameters in this rule (window times, liquidity pool definitions, FVG entry mechanics, target selection) are widely-circulated ICT heuristics and are tested empirically under the frozen rulebook / zero-training / MCPT gate.
- **Rule:**
  1. Setup MUST use an FVG (`zone.kind == "fvg"`). Order Blocks are prohibited for Silver Bullet.
  2. Entry Levels:
     - Model 1 (Conservative): Consequent Encroachment (CE - 50% midpoint of the FVG).
     - Model 2 (Aggressive): Proximal edge of the FVG ($L_3$ for bullish, $H_3$ for bearish).
  3. Cost Viability Gate:
     $$\text{FVG Height} \ge 2.0 \times \text{Spread}$$
     A gap smaller than twice the broker spread cannot yield positive net expectancy after entry/exit slippage.

### Rule SB-05: Target Selection Architecture
- **Classification:** `RESEARCH_HYPOTHESIS`
- **Transcript Citation:** None. Audit 1 (2026-11-03) found no Silver Bullet transcript file in the user's corpus. The parameters in this rule (window times, liquidity pool definitions, FVG entry mechanics, target selection) are widely-circulated ICT heuristics and are tested empirically under the frozen rulebook / zero-training / MCPT gate.
- **Rule:**
  1. Opposing Liquidity Target: The nearest unmitigated opposing swing high (for BUY) or swing low (for SELL) formed during the current session.
  2. Verification: If Opposing Target yields $R:R \ge 1.5$, set $\text{TP} = \text{Opposing Target}$.
  3. Structural Fallback Target: If no clean opposing swing point exists:
     - For `USATECHIDXUSD`: 15 index points (minimum 10-15 point delivery).
     - For `EURUSD` / `GBPUSD`: 20 pips (minimum 20-30 pip delivery).
     - Both must independently pass $R:R \ge 1.5$. If $R:R < 1.5$, the setup is REJECTED.

---

## 5. Summary Compliance Matrix

| Rule ID | Module | Strategy | Transcript Citation | Operational Status |
| :--- | :--- | :--- | :--- | :--- |
| **P-01** | `structure/bias` | Common | 2022 Mentorship Ep 19 [01:39:10] | `SOURCE_CONFIRMED` |
| **P-02** | `structure/amd` | Common | 2022 Mentorship Ep 9 [00:02:40] | `SOURCE_CONFIRMED` |
| **P-03** | `structure/mss` | Common | None (Audit 1 2026-11-03) | `SOURCE_INTERPRETATION` |
| **P-04** | `structure/fvg` | Common | None (Audit 1 2026-11-03) | `SOURCE_INTERPRETATION` |
| **JS-01** | `setups/judas` | Judas | Model 1 London Session Focus | `ENGINEERING_CONSTRAINT` |
| **JS-02** | `setups/judas` | Judas | Market Structure Lesson 14 ~[00:22:41] | `SOURCE_INTERPRETATION (structural); RESEARCH_HYPOTHESIS (EMA20 subrule)` |
| **JS-03** | `setups/judas` | Judas | None (Audit 1 2026-11-03) | `RESEARCH_HYPOTHESIS` |
| **JS-04** | `setups/judas` | Judas | London Timing Disaggregation | `ENGINEERING_CONSTRAINT` |
| **JS-05** | `setups/judas` | Judas | 2022 Mentorship Ep 9 [00:03:11] | `RESEARCH_HYPOTHESIS` |
| **JS-06** | `setups/judas` | Judas | Sweep Candle Extreme + Buffer | `ENGINEERING_CONSTRAINT` |
| **JS-07** | `setups/judas` | Judas | None (Audit 1 2026-11-03) | `SOURCE_INTERPRETATION` |
| **SB-01** | `setups/sb` | Silver Bullet | None (Audit 1 2026-11-03) | `RESEARCH_HYPOTHESIS` |
| **SB-02** | `setups/sb` | Silver Bullet | None (Audit 1 2026-11-03) | `RESEARCH_HYPOTHESIS` |
| **SB-03** | `setups/sb` | Silver Bullet | 2022 Mentorship Ep 10 [00:28:02] | `RESEARCH_HYPOTHESIS` |
| **SB-04** | `setups/sb` | Silver Bullet | None (Audit 1 2026-11-03) | `RESEARCH_HYPOTHESIS` |
| **SB-05** | `setups/sb` | Silver Bullet | None (Audit 1 2026-11-03) | `RESEARCH_HYPOTHESIS` |
