# QVM Contribution Experiments (Tax-Aware, Spain)

This document consolidates the recent contribution-based experiment variants, their return profile vs SPY, turnover behavior, and estimated Spanish capital-gains tax impact.

## Scope and setup

Backtest window and structure:

- Formation years: 2015 to 2025 (11 annual periods)
- Portfolio size: Top 10 names
- Rebalance date: April 1
- Cash contributions: 20,000 EUR initial + 2,000 EUR per year
- Benchmark: SPY
- Ranking mode: quality-only

Primary command used:

```bash
uv run qvm-contribution-experiments --start-year 2015 --end-year 2025 --top-n 10 --contribution-months 12 --initial-contribution 20000 --contribution-amount 2000 --output-dir data/qvm/backtest/contribution_portfolio_taxaware
```

Main comparison output:

- data/qvm/backtest/contribution_portfolio_taxaware/contribution_experiment_comparison.csv

## Experiment variants

The suite now includes the following contribution/rebalance policies:

1. Quality Only + Contributions
2. Quality Only + Contributions + Max 1 Replacement
3. Quality Only + Contributions + Max 1 Replacement + No Trims
4. Quality Only + Contributions + Max 1 Replacement + Soft Cap 15%
5. Quality Only + Contributions + Max 1->3 Adaptive + Soft Cap 15%
6. Quality Only + Contributions + Max 2 Replacements

Policy notes:

- reset_equal_weight: full equalization at each contribution/rebalance point.
- buy_biased_no_trim: avoid trimming persisted names; allocate cash to underweights/entrants.
- buy_biased_soft_cap: same as no-trim, but trims only the excess above a 15% position weight cap.
- limited_replacements_adaptive: max 1 replacement in normal years, but allows up to 3 when incumbents show sharp quality score drops (threshold 15 points).

## Return and turnover snapshot

From contribution_experiment_comparison.csv:

| Experiment | TWR CAGR | MWRR | Turnover | Win rate vs SPY |
|---|---:|---:|---:|---:|
| Quality Only + Contributions | 23.38% | 23.25% | 50.00% | 72.73% |
| Max 1 Replacement | 21.94% | 21.78% | 13.00% | 81.82% |
| Max 1 Replacement + No Trims | 20.94% | 20.66% | 13.00% | 90.91% |
| Max 1 Replacement + Soft Cap 15% | 21.34% | 21.08% | 13.00% | 90.91% |
| Max 1->3 Adaptive + Soft Cap 15% | 20.62% | 20.41% | 26.00% | 81.82% |
| Max 2 Replacements | 19.99% | 19.70% | 23.00% | 81.82% |

Interpretation:

- Full refresh still had the highest gross return but at very high turnover.
- Limiting replacements cut turnover materially.
- The no-trim variant reduced selling pressure but drifted weights heavily.
- Soft-cap recovered part of that drift while keeping turnover low.
- Adaptive mode reacted faster to quality shocks but raised turnover versus strict max-1 soft-cap.

## Shock-year backlog reduction (Adaptive vs Max-1 Soft Cap)

Question addressed: what happens if several holdings degrade in the same year.

Comparison file:

- data/qvm/backtest/contribution_portfolio_taxaware/adaptive_backlog_vs_max1_softcap.csv

Headline results:

- Average stale names vs full-refresh target:
   - Max-1 soft-cap: 4.36
   - Adaptive 1->3 soft-cap: 2.64
- Average improvement: 1.73 fewer stale names per year
- Max improvement in one year: 4 names
- Years improved: 9 of 11

Interpretation:

- Adaptive policy materially reduces backlog during multi-name deterioration years.
- The trade-off is higher turnover (26% vs 13% for strict max-1 soft-cap).

## Weight drift context (No Trims)

Observed in the no-trim diagnostics:

- Max post-rebalance drift from 10% target reached about 10.96 percentage points.
- Severe drift (>= 3 percentage points from target): 22 of 110 stock-year observations.
- Drift concentration mostly in 2017 to 2025.

## Tax estimate methodology (Spain)

A replay script estimates realized gains from strategy sells, then applies annual Spanish savings tax brackets:

- 0 to 6,000 EUR at 19%
- 6,000 to 56,000 EUR at 21%
- 56,000 to 256,000 EUR at 23%
- 256,000 to 556,000 EUR at 27%
- over 556,000 EUR at 28%

Script:

```bash
uv run python scripts/strategies/qvm/estimate_contribution_taxes_spain.py --base-dir data/qvm/backtest/contribution_portfolio_taxaware
```

Outputs:

- data/qvm/backtest/contribution_portfolio_taxaware/tax_and_returns_with_spy.csv
- data/qvm/backtest/contribution_portfolio_taxaware/tax_estimate_spain_comparison.csv
- data/qvm/backtest/contribution_portfolio_taxaware/<experiment>/tax_yearly_estimate_spain.csv

## Combined tax + return + SPY results

From tax_and_returns_with_spy.csv:

| Experiment | Portfolio TWR CAGR | SPY TWR CAGR | Tax total (EUR) | After-tax final value (EUR) |
|---|---:|---:|---:|---:|
| Quality Only + Contributions | 23.38% | 12.98% | 37,020.61 | 237,501.79 |
| Max 1 Replacement | 21.94% | 12.98% | 32,834.99 | 210,961.67 |
| Max 1 Replacement + No Trims | 20.94% | 12.98% | 10,125.87 | 212,388.98 |
| Max 1 Replacement + Soft Cap 15% | 21.34% | 12.98% | 9,574.87 | 220,786.75 |
| Max 1->3 Adaptive + Soft Cap 15% | 20.62% | 12.98% | 6,491.09 | 211,568.99 |
| Max 2 Replacements | 19.99% | 12.98% | 28,147.23 | 177,733.46 |

## Practical decision summary

Two ways to define best:

1. Highest after-tax ending value in this historical run:
   Quality Only + Contributions (full refresh).
2. Best tax-aware balance for a taxable account:
   Max 1 Replacement + Soft Cap 15%.
3. Best rule if your priority is faster cleanup in shock years:
   Max 1->3 Adaptive + Soft Cap 15%.

Why the tax-aware choice is often Soft Cap 15%:

- low turnover (13%)
- far lower tax bill than reset-equal variants
- stronger after-tax outcome than no-trim in this run

When adaptive may be preferable despite lower returns in this sample:

- you want a stricter risk-control response when many names deteriorate together
- you accept higher turnover to reduce stale holdings more quickly

## Caveats

This is a research estimate, not tax advice.

- It estimates capital-gains tax on realized gains from strategy transitions.
- It does not include broker fees, FX effects, dividend taxation, personal offsets/carryforwards, or other household gains/losses.
- Real-world tax depends on account history and investor-specific reporting context.
