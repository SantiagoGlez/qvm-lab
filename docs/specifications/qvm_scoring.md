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
| Strong trend + strong RS + no/little pullback | **Extended** |
| Strong trend, RS still catching up | **Improving** |
| Neutral trend + meaningful pullback | **Recovering** |
| Weak trend (regardless of other signals) | **Weak** |

---

## 4. Signals and Actions (Portfolio vs Watchlist Universe)

This section translates QVM outputs into portfolio decisions depending on whether a stock is already held or only monitored in the watchlist universe.

### Core signal fields

The action engine should evaluate the following fields for each stock:

| Field | Source | Purpose |
|---|---|---|
| `overall_score` | Valuation + Quality | Primary rank/filter signal |
| `valuation_band` | Historical P/E percentile | Position sizing and trim caution |
| `market_assessment` | Momentum composite | Timing/entry context |
| `in_portfolio` | Portfolio state | Route to holding vs candidate logic |

### Action labels

Use a small set of explicit actions:

| Action | Meaning |
|---|---|
| `BUY` | Open a new position (universe candidate) |
| `ADD` | Increase an existing position |
| `HOLD` | Keep position unchanged |
| `TRIM` | Reduce position size |
| `EXIT` | Close the position |
| `WATCH` | Keep in universe but do not initiate |
| `DROP` | De-prioritise/remove from active watchlist |

### A) Stocks already in portfolio (`in_portfolio = true`)

| Signal condition | Action | Rationale |
|---|---|---|
| `overall_score ≥ 80` and `market_assessment` in {Attractive, Improving} and `valuation_band` in {Deep Value, Cheap, Fair Value} | `ADD` | Strong fundamentals with supportive setup and acceptable valuation |
| `overall_score ≥ 70` and `market_assessment` in {Attractive, Improving, Recovering, Extended} | `HOLD` | Quality remains intact; no forced trading |
| `overall_score 55-69` or `market_assessment = Weak` | `TRIM` | Deterioration detected; reduce risk gradually |
| `overall_score < 55` and (`market_assessment = Weak` or `valuation_band` in {Expensive, Very Expensive}) | `EXIT` | Thesis breakdown and/or poor risk-reward |

### B) Stocks in watchlist universe (`in_portfolio = false`)

| Signal condition | Action | Rationale |
|---|---|---|
| `overall_score ≥ 80` and `market_assessment` in {Attractive, Improving} and `valuation_band` in {Deep Value, Cheap, Fair Value} | `BUY` | High-conviction entry candidate |
| `overall_score ≥ 70` and `market_assessment` in {Recovering, Extended} | `WATCH` | Good business, but timing not ideal yet |
| `overall_score 55-69` | `WATCH` | Keep on radar; wait for quality/valuation improvement |
| `overall_score < 55` or (`valuation_band = Very Expensive` and `market_assessment = Weak`) | `DROP` | Low expected edge relative to universe |

### Practical implementation notes

- Actions are guidance signals, not automatic orders.
- Recompute signals at each rebalance cycle (for example: monthly).
- `TRIM` and `EXIT` should still respect risk controls (max turnover, tax constraints, liquidity).
- If multiple stocks map to `BUY`, rank by `overall_score` first, then favour `Attractive` over `Improving`.

---

## Overall Score

```
overall_score = mean(valuation_score, quality_score)
```

Momentum is currently used as a qualitative filter / display column (`market_assessment`) and does not contribute to the numeric score.
