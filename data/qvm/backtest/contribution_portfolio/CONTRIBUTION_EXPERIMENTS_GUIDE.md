# Contribution Experiments Guide

This folder contains the periodic-contribution backtest outputs.

## What this run does

The contribution backtest keeps the stock selection annual, but adds new capital every two months inside each annual holding period.

It compares two strategies:

- Quality Only + Contributions
- Action Simplified: Overall>=75 + Not Very Expensive + Contributions

Both strategies receive the same contribution schedule and are benchmarked against SPY using the same dates.

## Where to see the results

- `contribution_experiment_comparison.csv`: one row per experiment with time-weighted and money-weighted results.
- `<experiment-folder>/audit.csv`: one row per holding per formation year.
- `<experiment-folder>/returns.csv`: one row per year with contribution count, portfolio return, benchmark return, and end values.
- `<experiment-folder>/cashflows.csv`: one row per contribution date showing how cash was deployed.
- `<experiment-folder>/selection_diagnostics.csv`: selection diagnostics for each annual rebalance.

## Experiment catalog

### Quality Only + Contributions
- scoring_mode: quality
- selection_policy: score
- rebalance: annual, April 1
- contribution schedule: every 2 months
- rule: rank by quality score only and invest equal-weight at each contribution date.

### Action Simplified: Overall>=75 + Not Very Expensive + Contributions
- scoring_mode: quality
- selection_policy: action_simplified_relaxed_score_band
- rebalance: annual, April 1
- contribution schedule: every 2 months
- rule: require overall score >= 75 and exclude Very Expensive bands, then rank by quality.

## How to read the comparison

- TWR CAGR tells you how the strategy itself performed independent of cash-flow timing.
- MWRR tells you how the actual contributed capital performed.
- If TWR and MWRR diverge, the contribution timing is affecting the investor experience.

## Quick reading tip

If selected_count is below 10 in `returns.csv`, that year was underfilled and the portfolio became more concentrated.