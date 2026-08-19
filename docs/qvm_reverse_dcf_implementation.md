# QVM Reverse DCF Implementation

## Business Purpose

Reverse DCF is designed to explain market expectations, not to produce another opaque score.

It complements the historical valuation view:

- Historical valuation asks: is the stock cheap or expensive versus its own historical range?
- Reverse DCF asks: what Free Cash Flow growth must happen for today's price to be justified?

This gives an expectations lens that can be compared with what the business has historically delivered.

## Core Concepts

### 1) Implied FCF Growth

The model solves for the annual growth rate that makes discounted cash flow value equal to the current market price.

- Higher implied growth means the market is pricing in stronger future execution.
- Lower implied growth means the market is demanding less future growth.

### 2) Representative Historical Growth

The model computes long-horizon growth rates and summarizes them with a median:

- Revenue CAGR: 5Y and 10Y
- EPS CAGR: 5Y and 10Y
- FCF CAGR: 5Y and 10Y

Then:

- Representative Growth = median of available growth inputs

Median is used instead of average to reduce sensitivity to single outliers.

### 3) Expectation Gap

- Expectation Gap = Representative Growth - Implied FCF Growth

Interpretation:

- Positive gap: market expectations are more conservative than historical delivery
- Negative gap: market expectations are more optimistic than historical delivery

## Robustness for Cyclical Names

Some cyclical companies show extreme historical CAGR values due to cycle rebounds or temporary peaks.

To make the benchmark more stable, each historical CAGR input is winsorized before the median step.

Current default cap range:

- Floor: -15%
- Ceiling: +25%

This is applied only to representative growth construction. The implied growth solver is unchanged.

## Assessment Thresholds

- Gap >= +6%: Very Conservative Expectations
- +3% to +6%: Conservative Expectations
- -3% to +3%: Reasonable Expectations
- -6% to -3%: Optimistic Expectations
- Gap < -6%: Very Optimistic Expectations

## Data Strategy

### Live Inputs (market-facing)

Primary source: Yahoo

- Current share price
- Shares outstanding (or inferred from market cap and price)
- TTM Free Cash Flow

### Historical Inputs (benchmark-facing)

Primary source: CompaniesMarketCap and SEC probe files in data/qvm/companiesmarketcap

- Revenue history: CompaniesMarketCap financials
- EPS history: CompaniesMarketCap financials
- FCF history: CompaniesMarketCap financials, then SEC CompanyFacts probe fallback

Yahoo history is available as a fallback when needed.

## History Quality Flag

A quality indicator is computed from available growth inputs:

- Input count: how many growth series are available
- Dispersion: max growth input minus min growth input

Quality labels:

- Limited: fewer than 3 inputs
- Stable: low dispersion
- Moderate: medium dispersion
- Volatile: high dispersion

This helps flag when interpretation should be more cautious.

## Output Fields

The Reverse DCF analysis includes:

- Implied FCF Growth
- Historical growth components (Revenue/EPS/FCF 5Y and 10Y)
- Representative Growth (capped median)
- Expectation Gap
- Assessment
- Notes metadata:
  - whether growth cap is active and cap range
  - history quality, input count, dispersion
  - source labels retained in model for auditability

## Implementation Map

Main implementation files:

- src/quantlab/strategies/qvm/intrinsic/reverse_dcf.py
- src/quantlab/strategies/qvm/providers/yahoo.py
- src/quantlab/strategies/qvm/models.py
- src/quantlab/strategies/qvm/reports/console.py

Validation tests:

- tests/formulas/test_reverse_dcf.py

## Known Trade-offs

- Capping improves stability in cyclicals but can dampen upside from true structural breakouts.
- Source differences (timing, fiscal-year labels, accounting mapping) can create small cross-provider mismatches.
- Reverse DCF remains a scenario framework, not a precise intrinsic value target.
