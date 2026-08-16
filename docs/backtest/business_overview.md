# QVM Backtest Business Overview

This document explains the business logic behind the backtest. It is intentionally written as a decision-oriented overview rather than a pure technical spec.

## Why we backtest

The goal is not to prove that a strategy is perfect in hindsight. The goal is to answer a more practical question:

## How we compare strategies

The comparison table is designed to make the strategy decision transparent. We do not only rank strategies by CAGR. We compare each variant on the same core dimensions so that a stronger result is not just a lucky outcome in one period.

The comparison fields are:

- `experiment`: the strategy or parameter variant being tested
- `scoring_mode`: which score family drives the ranking (`quality`, `valuation`, or `qv`)
- `formation_month` / `formation_day`: when the ranking is formed each year
- `top_n`: portfolio size
- `years`: number of annual samples in the run
- `cagr`: portfolio compound annual growth rate
- `sharpe`: risk-adjusted return measure
- `max_drawdown`: the largest decline in the period
- `turnover`: how much the portfolio changes from year to year
- `win_rate_vs_spy`: proportion of years the strategy beat SPY
- `spy_cagr`: benchmark return for context
- `excess_cagr`: portfolio outperformance over the benchmark

This is what lets us compare strategy quality in a disciplined way instead of relying on a single headline number.

When we use the quality score specifically, the metric inputs are the drivers behind the ranking: ROIC, ROE, operating margin, revenue CAGR, EPS CAGR, FCF margin, FCF conversion, and leverage / balance-sheet quality.

> Does the QVM ranking framework produce repeatable, explainable, and durable relative performance over real market cycles?

The backtest is used to test whether a portfolio built from Quality + Valuation signals can survive noisy fundamentals, changing market regimes, and uneven data availability.

## Core criteria

The backtest uses a set of explicit rules to keep the logic disciplined and interpretable:

- annual portfolio formation
- use of the previous available fundamentals at rebalance time
- selection of the top N companies by score
- equal-weight holding during the next 12 months
- benchmarking against SPY over the same annual period
- no use of future information

This means we are testing a capital allocation framework, not a real-time trading engine.

## How the backtest is conducted

### 1) Formation year

Each year acts as a formation point. At a fixed rebalance date (for example, April 1), the system evaluates all companies in the QVM universe using the quality and valuation inputs available up to that point.

### 2) Ranking

Companies are ranked using the existing production QVM scoring logic. The annual strategy selects the highest-ranking names for the portfolio.

### 3) Portfolio build

The selected names are treated as a simple equal-weight portfolio for the next year. The aim is to preserve the signal logic in a clean, testable way without over-engineering execution features.

### 4) Return measurement

Once the portfolio is formed, the strategy measures annual return using adjusted close prices. The same is done for SPY so the result can be evaluated relative to the benchmark.

### 5) Sensitivity checks

The project also tests whether the signal is robust by changing one variable at a time:

- formation month
- time windows
- portfolio size
- leave-one-year-out analysis

This is important because a strategy may look strong in a single period but fail once the sample is stress-tested.

## Interpretation of results

The backtest is read in three layers:

### 1) Absolute performance

Did the portfolio produce attractive long-term return characteristics, such as:

- strong CAGR
- healthy Sharpe ratio
- moderate drawdown
- a sensible win rate against the benchmark

### 2) Relative robustness

Does the signal hold when:

- a year is removed from the test set
- the rebalance date changes
- the portfolio size changes
- the sample window shifts

### 3) Economic explanation

The strongest quality portfolios are usually driven by durable fundamentals such as:

- ROIC
- ROE
- operating margin
- revenue growth
- EPS growth
- free cash flow conversion
- lower leverage and balance-sheet stress

This makes the result easier to explain to stakeholders: the strategy is not just buying “good-looking” companies; it is favoring firms with durable earnings power and capital discipline.

## Why this is useful

The backtest framework is valuable because it translates a subjective signal into a disciplined, repeatable process:

- it creates a transparent scorecard
- it supports comparison across strategies
- it reveals whether results are driven by a few inputs or by broad structural quality
- it helps highlight which metric exposures are responsible for the signal

## Limits

This is a research backtest, not a full trading simulation. It does not model:

- transaction costs
- taxes
- slippage
- portfolio constraints
- shorting or hedging
- live order execution

Those considerations are important later, but they are intentionally outside the first-stage research loop.

## Summary

The QVM backtest is built to answer a clean question: do strong quality and valuation characteristics, measured at annual formation points, translate into persistent outperformance over time when tested in a simple, explainable portfolio process?

If the answer remains stable across time windows and portfolio sizes, the signal is more credible as a genuine investment edge rather than a single-period anomaly.

For the implementation and command workflow, see [README.md](README.md).
