# QVM turnover-hysteresis rebalance policy

## Goal

This policy keeps the original quality-only ranking rule intact, while reducing churn caused by tiny score differences around the selection boundary. It is intentionally implemented as a separate selection policy so the earlier logic remains available for comparison and regression testing.

## Policy design

### 1) Hold buffer

The strategy protects a wider band of names from being sold immediately. Instead of selling purely on the basis of the current top-10 rank, it keeps previously held names while they remain in a protected zone.

Default settings:
- keep_top_n = 15
- top_n = 10

This means names ranked between 1 and 15 are treated as protected until they fall far enough outside the signal band to merit replacement.

### 2) Minimum replacement score gap

A new candidate is only allowed to replace an incumbent when the quality improvement is materially larger than the noise that typically exists around the boundary.

Default settings:
- min_gap = 2.0 quality points

This prevents a portfolio from rotating on tiny score differences that are often not economically meaningful.

## Why this is useful

In the historical Universe 130 Quality Only strategy, the churn rate is high because many replacements occur at nearly identical quality scores. The result is a portfolio that is technically re-ranked every year, but not necessarily meaningfully improved.

The hysteresis rule addresses that by:
- retaining stable winners near the cut line,
- requiring a real quality gap before a replacement is made,
- preserving signal while lowering unnecessary turnover.

## Implementation

The legacy strategy remains available as the original score-based policy. The new logic is implemented separately:
- `select_companies_quality_hysteresis(...)`
- `selection_policy = "quality_hysteresis"`

The baseline rebalance logic is still preserved in the older `score` and `quality_soft_valuation_guard` selection paths.

## Backtest result summary

At the time of validation, the new policy produced:
- CAGR: 24.20%
- Sharpe: 1.1385
- Max drawdown: -3.52%
- Turnover: 49.00%
- Win rate vs SPY: 81.82%
- Excess CAGR vs SPY: 11.22%

This compares favorably with the original quality-only policy while keeping turnover in the same general range, but with a more disciplined replacement rule.

## Files

- policy implementation: `src/quantlab/strategies/qvm/backtest/annual.py`
- CLI experiment list: `src/qvm_lab/cli.py`
- comparison output: `data/qvm/backtest/experiments_universe_130/experiment_comparison.csv`
