# QVM Scoring — Criteria Reference

The QVM strategy evaluates each company across three pillars: **Valuation**, **Quality**, and **Momentum (Market Assessment)**. Each pillar produces a score from 0–100. The overall score is currently the average of Valuation and Quality (Momentum is qualitative only).

---

## 1. Valuation

> _Is the stock cheap or expensive relative to its own history?_

**Data source:** Historical P/E series (companiesmarketcap) + forward/trailing P/E (Yahoo Finance).

### Sub-scores and weights

| Sub-score | Weight | Description |
|---|---|---|
| Historical P/E Percentile | 60% | Where does the current P/E sit within its own 10-year history? Low percentile = historically cheap. Score = `100 − (percentile × 100)` |
| Discount to Historical Average | 25% | How far is forward P/E from the historical average (or median) P/E? Score = `100 − │(fwdPE / avgPE − 1)│ × 100` |
| Forward vs Trailing PE | 15% | Earnings growth signal: a lower forward P/E than trailing implies accelerating earnings. |

### Forward vs Trailing PE scoring

| fwdPE / trailingPE | Score |
|---|---|
| ≤ 0.80 | 100 |
| ≤ 0.90 | 90 |
| ≤ 1.00 | 80 |
| ≤ 1.10 | 70 |
| > 1.10 | 50 |

### Valuation bands (from historical percentile)

| Percentile | Band |
|---|---|
| < 20% | Deep Value |
| 20–40% | Cheap |
| 40–60% | Fair Value |
| 60–80% | Expensive |
| 80–100% | Very Expensive |

---

## 2. Quality

> _Is this a high-quality, durable business?_

**Data source:** Yahoo Finance (fundamentals).

### Sub-scores and weights

| Metric | Weight | What it measures |
|---|---|---|
| ROIC | 25% | Return on Invested Capital — capital efficiency |
| EPS CAGR | 15% | Earnings-per-share growth rate (annualised) |
| Revenue CAGR | 10% | Revenue growth rate (annualised) |
| FCF Margin | 10% | Free Cash Flow as % of revenue |
| FCF Conversion | 10% | FCF / Net Income — earnings quality |
| Net Debt / EBITDA | 10% | Balance sheet leverage |
| Leverage (Interest Coverage or Debt/EBITDA) | 10% | Debt serviceability; uses Interest Coverage when available, Debt/EBITDA as fallback |
| Operating Margin | 5% | Profitability of core operations |
| ROE | 5% | Return on Equity |

### Scoring thresholds per metric

**ROIC**

| ROIC | Score |
|---|---|
| ≥ 25% | 100 |
| ≥ 15% | 85 |
| ≥ 10% | 70 |
| ≥ 5% | 50 |
| < 5% | 25 |

**ROE**

| ROE | Score |
|---|---|
| ≥ 30% | 100 |
| ≥ 20% | 85 |
| ≥ 15% | 70 |
| ≥ 10% | 50 |
| < 10% | 25 |

**Operating Margin**

| Op. Margin | Score |
|---|---|
| ≥ 30% | 100 |
| ≥ 20% | 85 |
| ≥ 15% | 70 |
| ≥ 10% | 50 |
| < 10% | 25 |

**Revenue CAGR / EPS CAGR**

| CAGR | Score |
|---|---|
| ≥ 20% | 100 |
| ≥ 15% | 85 |
| ≥ 10% | 70 |
| ≥ 5% | 50 |
| ≥ 0% | 25 |
| < 0% | 0 |

**FCF Margin**

| FCF Margin | Score |
|---|---|
| ≥ 20% | 100 |
| ≥ 15% | 85 |
| ≥ 10% | 70 |
| ≥ 5% | 50 |
| ≥ 0% | 25 |
| < 0% | 0 |

**FCF Conversion** (FCF / Net Income)

| Conversion | Score |
|---|---|
| ≥ 100% | 100 |
| ≥ 80% | 85 |
| ≥ 60% | 70 |
| ≥ 40% | 50 |
| ≥ 0% | 25 |
| < 0% | 0 |

**Net Debt / EBITDA** (lower/negative = better)

| Net Debt/EBITDA | Score |
|---|---|
| ≤ 0 (net cash) | 100 |
| ≤ 0.5× | 85 |
| ≤ 1.5× | 70 |
| ≤ 3.0× | 50 |
| > 3.0× | 25 |

**Interest Coverage** (EBIT / Interest Expense)

| Coverage | Score |
|---|---|
| ≥ 15× | 100 |
| ≥ 10× | 85 |
| ≥ 5× | 70 |
| ≥ 3× | 50 |
| ≥ 1× | 25 |
| < 1× | 0 |

**Debt / EBITDA** (fallback for leverage when Interest Coverage is unavailable)

| Debt/EBITDA | Score |
|---|---|
| ≤ 0 (net cash) | 100 |
| ≤ 0.5× | 85 |
| ≤ 1.5× | 70 |
| ≤ 3.0× | 50 |
| > 3.0× | 25 |

### Quality recommendation labels

| Score | Label |
|---|---|
| ≥ 90 | Excellent |
| ≥ 75 | Good |
| ≥ 60 | Average |
| < 60 | Weak |

---

## 3. Momentum (Market Assessment)

> _Is the stock in a favourable technical position to enter?_

**Data source:** Yahoo Finance daily prices (2-year history). Qualitative only — no numeric score fed into the overall average.

### Three signals

#### Trend
_Price position relative to moving averages._

| Condition | Label |
|---|---|
| Price > SMA50 > SMA200 | Excellent |
| Price > SMA200 (but SMA50 not aligned) | Strong |
| Price within ±2% of SMA200 | Neutral |
| Price < SMA200 (beyond ±2% band) | Weak |

#### Relative Strength vs SPY
_Average of 6M and 12M excess return over SPY._

| Avg RS (stock − SPY) | Label |
|---|---|
| > +20% | Excellent |
| > +10% | Strong |
| −10% to +10% | Neutral |
| < −10% | Weak |

#### Pullback (Distance from 52-week High)
_Entry opportunity signal: healthy pullbacks from highs are ideal._

| Distance from 52W High | Label |
|---|---|
| ≥ 0% (at or above high) | New High |
| 0% to −10% | Neutral |
| −10% to −20% | Excellent |
| −20% to −35% | Strong |
| < −35% | Weak |

### Overall Market Assessment

Combines all three signals into a single label:

| Condition | Assessment |
|---|---|
| Strong trend + strong RS + healthy pullback | **Attractive** |
| Strong trend + strong RS + no/little pullback | **Near-highs** |
| Strong trend, RS still catching up | **Improving** |
| Neutral trend + meaningful pullback | **Recovering** |
| Weak trend (regardless of other signals) | **Weak** |

---

## 4. Signals and Actions (Portfolio vs Watchlist Universe)

This section translates QVM outputs into portfolio decisions depending on whether a stock is already held or only monitored in the watchlist universe.

Important distinction:
- The current implementation uses a simpler action layer.
- The framework below is the intended decision model for live portfolio management because it aligns better with the stronger backtest evidence: quality-first selection, low-turnover replacement, and valuation used as a secondary modifier.

### Core signal fields

The decision engine should evaluate the following fields for each stock:

| Field | Source | Purpose |
|---|---|---|
| `quality_score` | Quality model | Primary inclusion and ranking signal |
| `valuation_band` / `valuation_score` | Historical P/E percentile | Preference, tie-breaks, trim caution |
| `intrinsic_valuation` | Reverse DCF assessment | Sanity check, secondary ranking tilt |
| `market_assessment` | Momentum composite | Timing/entry context |
| `in_portfolio` | Portfolio state | Route to holding vs candidate logic |

The intended roles are:
- `quality_score`: decides most of who belongs in the portfolio.
- `historical_valuation`: soft filter and ranking aid, not the main engine.
- `intrinsic_valuation`: higher-level cross-check; best used as a modest tilt, not a hard gate.
- `market_assessment`: controls pace of entry and sizing urgency, not necessarily inclusion.

### Action buckets

Use separate action buckets for owned names and external candidates.

#### Portfolio buckets (`in_portfolio = true`)

| Action | Meaning |
|---|---|
| `KEEP` | Thesis intact; no action needed beyond routine monitoring |
| `KEEP (MONITOR)` | Thesis intact but with mild caution; keep position and monitor before moving to `REVIEW` |
| `ADD` | Existing holding remains a top candidate; add normally |
| `ADD_SLOW` | Existing holding remains attractive, but add gradually |
| `REVIEW` | Possible funding source for a stronger candidate |
| `EXIT` | Thesis broken or clearly dominated by stronger alternatives |

Optional portfolio warning:
- `REDUCE` is not a primary decision bucket.
- Use it only as a concentration-control warning, for example when a position grows materially above the intended weight cap.
- It should not be triggered by market weakness alone.

#### Watchlist buckets (`in_portfolio = false`)

| Action | Meaning |
|---|---|
| `ADD` | Open a new position now with normal sizing (high-conviction entry) |
| `ADD_SLOW` | Open a starter or build gradually |
| `CANDIDATE TO ADD` | Not a full `ADD` today, but first reserve list when true `ADD` names are limited |
| `WATCH` | Keep on radar, but do not commit capital yet |
| `REJECT` | Not attractive enough relative to alternatives |

### Reason content requirements (all actions)

Action reasons should always report nuanced context from the full signal set, not a single pass/fail trigger.

Every reason string should explicitly state:
- quality stance (`quality_score` level and direction)
- historical valuation stance (`valuation_band` / percentile context)
- intrinsic stance (`intrinsic_valuation` support, neutral, or warning)
- market stance (`market_assessment` and whether it affects pace vs inclusion)
- ownership context (`in_portfolio` true/false and why that route matters)

This makes `ADD` vs `ADD_SLOW` vs `CANDIDATE TO ADD`, and `KEEP` vs `KEEP (MONITOR)` vs `REVIEW`, explainable without hidden thresholds.

For company update reporting, this nuance should be visible directly in the stock output:
- `KEEP (MONITOR)` must state the specific mild warning and why it is not yet a replacement case.
- `REVIEW` must state what changed versus the stronger alternatives and why it is now a funding candidate.

### A) Stocks already in portfolio (`in_portfolio = true`)

| Typical condition | Action | Rationale |
|---|---|---|
| High quality, no major valuation warning, thesis still sound | `KEEP` | Quality remains the main reason to own the business |
| High quality remains intact, but one mild warning is present (for example expensive historical valuation or weak market tape) without thesis break | `KEEP (MONITOR)` | Keep the position, surface caution, and monitor for either re-upgrade to `KEEP` or downgrade to `REVIEW` |
| High quality, historical valuation acceptable, intrinsic supportive, market in {Attractive, Improving} | `ADD` | Strong business with supportive setup and acceptable valuation |
| High quality, historical valuation acceptable, intrinsic supportive, market in {Recovering, Neutral} | `ADD_SLOW` | Good candidate, but entry timing is less favorable |
| Quality slipping relative to better candidates, or valuation stretched, or market weak enough to lower conviction | `REVIEW` | Keep as a possible funding source for a stronger replacement |
| Thesis broken, quality weak/broken, or clearly inferior to current alternatives | `EXIT` | Capital should be recycled into higher-conviction opportunities |

Notes:
- `REVIEW` is not an automatic sell signal.
- `KEEP (MONITOR)` is the buffer state between `KEEP` and `REVIEW` when conviction is still positive but no longer clean.
- In a low-turnover process, `REVIEW` means the name is first in line if one replacement is justified.
- A weak market alone should not force an exit from a strong high-quality business.
- `REDUCE` should be reserved for overweight control rather than thesis management.

### B) Stocks in watchlist universe (`in_portfolio = false`)

Suggested threshold guardrails for watchlist actions:
- Quality tiers:
	- Excellent: `quality_score >= 75`
	- Average: `55 <= quality_score < 75`
	- Weak: `quality_score < 55`
- Historical valuation supportive: valuation band in {`Deep Value`, `Cheap`, `Fair Value`}.
- Intrinsic supportive: intrinsic assessment in {`Very Conservative Expectations`, `Conservative Expectations`, `Reasonable Expectations`}.
- Major valuation warning: historical valuation = `Very Expensive`.

| Typical condition | Action | Rationale |
|---|---|---|
| Excellent quality, market in {Attractive, Improving}, and valuation confirmation is strong (both valuation lenses supportive, or one supportive while the other is not a warning) | `ADD` | Highest-conviction immediate deployment bucket |
| Excellent quality, market in {Recovering, Neutral}, and at least one valuation lens supportive without double-warning | `ADD_SLOW` | Good business and acceptable setup, but build exposure gradually |
| Excellent quality, market in {Attractive, Improving, Recovering, Neutral}, and valuation is supportive but only partially confirmed | `CANDIDATE TO ADD` | Prioritized reserve list for near-add cases when `ADD` names are few |
| Reasonable candidate, but clearly weaker than current top opportunities and below candidate priority | `WATCH` | Monitor without committing capital today |
| Weak quality or too much valuation risk relative to better options | `REJECT` | Preserve attention and capital for stronger names |

Example:
- A stock can be `ADD_SLOW` even if it is not yet `ADD` because quality and valuation are supportive while market confirmation is incomplete.
- This is often the right bucket for names like META when business quality and valuation look compelling but momentum still reads as recovering.
- A stock can be `CANDIDATE TO ADD` when quality is excellent and market context is decent, but valuation confirmation is mixed (for example, one valuation lens warns while the other supports).
- A stock can still be `ADD` with one non-ideal valuation lens only if the other valuation lens is supportive and there is no double-warning; the reason should state that trade-off explicitly.

### Practical implementation notes

- Actions are guidance signals, not automatic orders.
- Recompute the full decision set at each review cycle.
- For the live portfolio, a two-month review cadence is a reasonable default because it fits the contribution workflow already tested.
- In practice, new cash should do most of the portfolio migration work.
- Replacements should be limited unless the thesis is clearly broken.
- If a position becomes too large, prefer surfacing a concentration warning before recommending any trim.

Suggested live review workflow every two months:
1. Add fresh cash.
2. Classify owned names as `KEEP`, `KEEP (MONITOR)`, `ADD`, `ADD_SLOW`, `REVIEW`, or `EXIT`.
3. Classify non-owned names as `ADD`, `ADD_SLOW`, `CANDIDATE TO ADD`, `WATCH`, or `REJECT`.
4. Allocate new cash to the best `ADD` and `ADD_SLOW` names first; use `CANDIDATE TO ADD` only when high-conviction `ADD` capacity is limited.
5. Allow at most one replacement unless a holding is clearly broken.
6. Use `REVIEW` names as the primary funding source if a replacement is justified.

This workflow is closer to the stronger backtest families than a full-refresh annual rebalance. In particular, it better matches the lower-turnover quality-first contribution variants with limited replacements.

---

## Overall Score

```
overall_score = mean(valuation_score, quality_score)
```

Momentum is currently used as a qualitative filter / display column (`market_assessment`) and does not contribute to the numeric score.
