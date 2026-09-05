# Contribution Experiments Guide

This folder contains the periodic-contribution backtest outputs.

## What this run does

The contribution backtest keeps the stock selection annual, but adds new capital every two months inside each annual holding period.

It compares quality-only contribution variants with different rebalance and allocation policies.

All variants receive the same contribution schedule and are benchmarked against SPY using the same dates.

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

### Quality Only + Contributions + Max 1 Replacement
- scoring_mode: quality
- selection_policy: score
- rebalance: annual, April 1
- contribution schedule: every 2 months
- rebalance policy: limited_replacements (max 1)
- allocation policy: reset_equal_weight

### Quality Only + Contributions + Max 1 Replacement + No Trims
- scoring_mode: quality
- selection_policy: score
- rebalance: annual, April 1
- contribution schedule: every 2 months
- rebalance policy: limited_replacements (max 1)
- allocation policy: buy_biased_no_trim

### Quality Only + Contributions + Max 1 Replacement + Soft Cap 15%
- scoring_mode: quality
- selection_policy: score
- rebalance: annual, April 1
- contribution schedule: every 2 months
- rebalance policy: limited_replacements (max 1)
- allocation policy: buy_biased_soft_cap (15% soft trim cap)

### Quality Only + Contributions + Max 1->3 Adaptive + Soft Cap 15%
- scoring_mode: quality
- selection_policy: score
- rebalance: annual, April 1
- contribution schedule: every 2 months
- rebalance policy: limited_replacements_adaptive (base max 1, can escalate to 3)
- allocation policy: buy_biased_soft_cap (15% soft trim cap)

### Quality Only + Contributions + Sep Dip Deploy
- scoring_mode: quality
- selection_policy: score
- rebalance: annual, April 1 (limited replacements: max 1)
- contribution schedule: every 2 months
- allocation policy: buy_biased_seasonal_dip_deploy
- rule: keep a cash buffer by deploying only a base fraction of available cash on regular contribution dates.
- rule: once per annual cycle, at or after September, if SPY drawdown from the cycle peak is at least 8%, deploy accumulated cash.
- rule: deployment is tilted to names with higher quality and improved valuation proxy (price down vs period start).

## How to read the comparison

- TWR CAGR tells you how the strategy itself performed independent of cash-flow timing.
- MWRR tells you how the actual contributed capital performed.
- If TWR and MWRR diverge, the contribution timing is affecting the investor experience.

## Quick reading tip

If selected_count is below 10 in `returns.csv`, that year was underfilled and the portfolio became more concentrated.