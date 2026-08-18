# Experiments Guide

This folder contains annual backtest experiment outputs for the universe_130 run.

## Where to see holdings

For each experiment, holdings are in that experiment folder's audit.csv file.

- audit.csv: one row per holding per formation year, including rank, ticker, scores, buy and sell dates, prices, and annual_return.
- returns.csv: one row per formation year with selected_count, portfolio_return, benchmark_return, and excess_return.
- experiment_comparison.csv: one row per experiment with summary metrics (CAGR, Sharpe, Max Drawdown, Turnover, Win Rate vs SPY).

Important note for Action Simplified experiments:

- Summary rows are in experiment_comparison.csv.
- Detailed files are now in permanent folders in this directory:
  - action_simplified:_overall>=80_+_fair_cheap_deep/audit.csv
  - action_simplified:_overall>=80_+_not_very_expensive/audit.csv
  - action_simplified:_overall>=75_+_not_very_expensive/audit.csv

## Experiment catalog

### Valuation Only Apr-01
- Name: Valuation Only Apr-01
- scoring_mode: valuation
- selection_policy: score
- Rule: rank by valuation score only and take top 10.
- Output folder: valuation_only_apr-01

### Quality Only Apr-01
- Name: Quality Only Apr-01
- scoring_mode: quality
- selection_policy: score
- Rule: rank by quality score only and take top 10.
- Output folder: quality_only_apr-01

### QV Baseline Apr-01
- Name: QV Baseline Apr-01
- scoring_mode: qv
- selection_policy: score
- Rule: rank by blended valuation and quality score and take top 10.
- Output folder: qv_baseline_apr-01

### QV Jan Rebalance
- Name: QV Jan Rebalance
- scoring_mode: qv
- selection_policy: score
- Rule: same as QV baseline, but rebalance in January.
- Output folder: qv_jan_rebalance

### Quality Only Jan Rebalance
- Name: Quality Only Jan Rebalance
- scoring_mode: quality
- selection_policy: score
- Rule: same as quality-only, but rebalance in January.
- Output folder: quality_only_jan_rebalance

### Quality + Soft Valuation Guard (>=20)
- Name: Quality + Soft Valuation Guard (>=20)
- scoring_mode: quality
- selection_policy: quality_soft_valuation_guard
- Rule: quality-first ranking with a minimum valuation floor of 20.
- Output folder: quality_+_soft_valuation_guard_(>=20)

### Quality + Soft Valuation Guard (>=30)
- Name: Quality + Soft Valuation Guard (>=30)
- scoring_mode: quality
- selection_policy: quality_soft_valuation_guard
- Rule: quality-first ranking with a minimum valuation floor of 30.
- Output folder: quality_+_soft_valuation_guard_(>=30)

### Quality + Soft Valuation Guard (>=40)
- Name: Quality + Soft Valuation Guard (>=40)
- scoring_mode: quality
- selection_policy: quality_soft_valuation_guard
- Rule: quality-first ranking with a minimum valuation floor of 40.
- Output folder: quality_+_soft_valuation_guard_(>=40)

### Quality -> Cheapest Half
- Name: Quality -> Cheapest Half
- scoring_mode: quality
- selection_policy: quality_cheapest_half
- Rule: filter to cheaper half by valuation, then rank by quality and take top 10.
- Output folder: quality_->_cheapest_half

### Quality + Buy/Hold Signals
- Name: Quality + Buy/Hold Signals
- scoring_mode: quality
- selection_policy: portfolio_signal
- Rule: allow only Buy, Hold, or Accumulate actions, then rank by quality.
- Output folder: quality_+_buy_hold_signals

### Action Simplified: Overall>=80 + Fair/Cheap/Deep
- Name: Action Simplified: Overall>=80 + Fair/Cheap/Deep
- scoring_mode: quality
- selection_policy: action_simplified_strict_band
- Rule: require overall score >= 80 and valuation band in Fair Value, Cheap, or Deep Value; then rank by quality.
- Output folder: action_simplified:_overall>=80_+_fair_cheap_deep

### Action Simplified: Overall>=80 + Not Very Expensive
- Name: Action Simplified: Overall>=80 + Not Very Expensive
- scoring_mode: quality
- selection_policy: action_simplified_relaxed_band
- Rule: require overall score >= 80 and exclude Very Expensive band; then rank by quality.
- Output folder: action_simplified:_overall>=80_+_not_very_expensive

### Action Simplified: Overall>=75 + Not Very Expensive
- Name: Action Simplified: Overall>=75 + Not Very Expensive
- scoring_mode: quality
- selection_policy: action_simplified_relaxed_score_band
- Rule: require overall score >= 75 and exclude Very Expensive band; then rank by quality.
- Output folder: action_simplified:_overall>=75_+_not_very_expensive

## Quick reading tip

If selected_count is below 10 in returns.csv for some years, the portfolio was underfilled that year and became more concentrated.
