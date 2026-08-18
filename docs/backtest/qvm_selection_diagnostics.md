# QVM Selection Diagnostics

## Purpose

Selection diagnostics explain what the strategy selected relative to what was available in the eligible universe each rebalance year.

This helps answer questions such as:
- Are we selecting cheaper names than the universe, or richer names?
- Is the quality edge large and stable?
- Are results driven by data coverage differences?
- Is the universe itself more expensive in some years?

## Output file

The annual backtest now writes:
- data/qvm/backtest/<run_output_dir>/selection_diagnostics.csv

For the current quality-only focus run:
- data/qvm/backtest/quality_only_apr01_focus/selection_diagnostics.csv

## Variable definitions

### Scope and counts

- formation_year: rebalance year.
- universe_n: number of eligible companies in that year after quality eligibility filtering.
- selected_n: number of selected holdings for the portfolio in that year.

### Valuation level (score-based)

Important: valuation medians are medians of valuation score, not medians of raw P/E.

In this framework:
- Higher valuation score means more attractive or less expensive versus own history.
- Lower valuation score means less attractive or more expensive versus own history.

Fields:
- universe_val_median: median valuation score of the eligible universe.
- selected_val_median: median valuation score of selected holdings.
- val_median_spread: selected_val_median minus universe_val_median.
  - Positive: selected names are cheaper on the valuation score scale.
  - Negative: selected names are richer on the valuation score scale.
- selected_val_median_pct_in_universe: percentile position of selected valuation median inside the universe valuation-score distribution.

### Valuation breadth by bands

- universe_expensive_share: share of universe in Expensive or Very Expensive bands.
- selected_expensive_share: share of selected holdings in Expensive or Very Expensive bands.
- expensive_share_spread: selected_expensive_share minus universe_expensive_share.
  - Negative is generally favorable.

- universe_cheap_share: share of universe in Deep Value or Cheap bands.
- selected_cheap_share: share of selected holdings in Deep Value or Cheap bands.
- cheap_share_spread: selected_cheap_share minus universe_cheap_share.
  - Positive is generally favorable.

### Quality edge

- universe_quality_median: median quality score of the eligible universe.
- selected_quality_median: median quality score of selected holdings.
- quality_median_spread: selected_quality_median minus universe_quality_median.
  - Positive means the strategy is selecting higher-quality companies than the universe median.

### Coverage bias check

- universe_coverage_median: median quality-data coverage in the eligible universe.
- selected_coverage_median: median quality-data coverage in selected holdings.
- coverage_median_spread: selected_coverage_median minus universe_coverage_median.
  - Large positive values can indicate coverage bias.
  - Near-zero values indicate less bias from data availability.

## How to run

### 1) Quality-only backtest focused run

Use this command from repository root:

  uv run qvm-backtest --scoring-mode quality --top-n 10 --formation-month 4 --formation-day 1 --start-year 2015 --end-year 2025 --output-dir data/qvm/backtest/quality_only_apr01_focus

This writes:
- audit.csv
- returns.csv
- selection_diagnostics.csv

all inside data/qvm/backtest/quality_only_apr01_focus.

### 2) Experiment suite runs

If you run qvm-experiments, each experiment output directory also writes its own selection_diagnostics.csv.

### 3) Current-year selection + universe regime comparison (single command)

Use the dedicated command below to:
- diagnose the current year selection (defaults to current calendar year), and
- generate a universe-only valuation regime table across a year range.

Example with explicit target year:

  uv run qvm-selection-diagnostics --year 2026 --top-n 10 --scoring-mode quality --selection-policy score --start-year 2015 --end-year 2026

Example using the default current calendar year (no --year needed):

  uv run qvm-selection-diagnostics --top-n 10 --scoring-mode quality --selection-policy score --start-year 2015 --end-year 2026

If you want to override target year with another value:

  uv run qvm-selection-diagnostics --year 2027 --top-n 10 --scoring-mode quality --selection-policy score --start-year 2015 --end-year 2027

Outputs:
- data/qvm/backtest/selection_diagnostics/selection_diagnostics_<year>.csv
- data/qvm/backtest/selection_diagnostics/universe_valuation_regime_by_year.csv

For example, with the current setup, generated files include:
- data/qvm/backtest/selection_diagnostics/selection_diagnostics_2026.csv
- data/qvm/backtest/selection_diagnostics/universe_valuation_regime_by_year.csv

The command also prints:
- target year summary,
- top 3 rich years (highest universe_expensive_share),
- top 3 cheap years (highest universe_cheap_share).

### 4) Quick test validation

  .venv/bin/pytest tests/backtest/test_annual_portfolio.py -q

## Interpretation for the current quality-only Apr-01 focus run

Source:
- data/qvm/backtest/quality_only_apr01_focus/selection_diagnostics.csv

Observed summary (2015-2025):
- Average val_median_spread: +8.93
- Average quality_median_spread: +23.24
- Average coverage_median_spread: -0.025
- Average universe_expensive_share: 0.686
- Average selected_expensive_share: 0.527
- Average universe_cheap_share: 0.205
- Average selected_cheap_share: 0.345
- Years with positive val_median_spread: 8
- Years with negative val_median_spread: 3

Reading:
- Quality selection edge is strong and persistent: selected quality medians are far above universe medians.
- On average, selected holdings are cheaper than the eligible universe on the valuation score framework.
- The selected basket is less concentrated in expensive bands and more represented in cheap bands than the universe.
- Coverage spread is close to zero overall, which suggests the result is not mainly a data-coverage artifact.
- Some years still show negative valuation spread, which indicates regime sensitivity and motivates monitoring year-by-year valuation context.

## Practical guidance

Use these diagnostics together with return outcomes:
- If quality spread is high but valuation spread turns negative for several consecutive years, expected forward risk may rise.
- If universe_expensive_share itself is high, the whole opportunity set may be rich, not only the selected names.
- If selected_n drops materially below target in other policies, performance interpretation should separate selection quality from exposure level effects.

## Related files

- src/quantlab/strategies/qvm/backtest/annual.py
- src/qvm_lab/cli.py
- tests/backtest/test_annual_portfolio.py
- data/qvm/backtest/quality_only_apr01_focus/selection_diagnostics.csv
