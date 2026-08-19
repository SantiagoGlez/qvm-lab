# QVM Backtesting Guide

This section explains how to run the QVM historical backtests and experiment suites in this repository.

For the business framing and decision criteria behind the backtest itself, see [business_overview.md](business_overview.md).

## What the backtest does

The repository runs a simple, annual backtest that:

- ranks companies using the production QVM scoring logic
- forms a portfolio on a fixed annual rebalance date
- selects the top N names for the next 12 months
- measures portfolio return against SPY over the same period
- aggregates outcomes like CAGR, Sharpe, drawdown, win rate, and turnover

This is designed for research and sensitivity testing, not for live execution or trading automation.

## Common commands

From the repository root:

```bash
uv sync
```

### 1) Single annual backtest run

```bash
uv run qvm-backtest --start-year 2015 --end-year 2025 --formation-month 4 --formation-day 1 --top-n 10
```

This writes audit and return files under:

```text
data/qvm/backtest/annual_portfolio/
```

Artifacts:

- `audit.csv` — selected company rows, scores, and annual returns
- `returns.csv` — yearly portfolio vs benchmark results

### 2) Strategy experiment comparison

```bash
uv run qvm-experiments --start-year 2015 --end-year 2025 --top-n 10 --output-dir data/qvm/backtest/experiments
```

This compares multiple experiment variants, for example:

- valuation only
- quality only
- combined QV
- alternate rebalance months

The comparison table is written to:

```text
data/qvm/backtest/experiments/experiment_comparison.csv
```

### 2b) Periodic contribution comparison

```bash
uv run qvm-contribution-experiments --start-year 2015 --end-year 2025 --top-n 10 --output-dir data/qvm/backtest/contribution_portfolio
```

This compares the quality-only strategy against the relaxed action rule using periodic contributions every two months.

Generated files include:

```text
data/qvm/backtest/contribution_portfolio/contribution_experiment_comparison.csv
```

See the dedicated guide for this run:

- [CONTRIBUTION_EXPERIMENTS_GUIDE.md](../../data/qvm/backtest/contribution_portfolio/CONTRIBUTION_EXPERIMENTS_GUIDE.md)

### 3) Quality-only battle testing

```bash
uv run qvm-quality-battletest --start-year 2015 --end-year 2025 --top-n 10 --output-dir data/qvm/backtest/experiments/quality_battletest
```

This runs:

- quality baseline
- time-window variations
- rebalance-month variations
- Top 5/10/15/20 portfolios
- leave-one-year-out robustness analysis

Generated files include:

```text
data/qvm/backtest/experiments/quality_battletest/quality_one_factor/experiment_comparison.csv
data/qvm/backtest/experiments/quality_battletest/quality_leave_one_year_out.csv
```

### 4) Quality diagnostics

```bash
uv run qvm-quality-diagnostics --start-year 2015 --end-year 2025 --top-n 15 --output-dir data/qvm/backtest/experiments/quality_diagnostics
```

This produces the mechanism-level diagnostics:

```text
data/qvm/backtest/experiments/quality_diagnostics/quality_effective_weights.csv
data/qvm/backtest/experiments/quality_diagnostics/quality_ablation_comparison.csv
```

These are used to answer:

- which quality metrics are truly driving the score
- whether dropping one quality factor materially changes results
- how much the score is diluted by missing data

## Comparison table fields explained

The experiment comparison tables are the main research output for strategy comparison. Each row represents one backtest variant and each column explains a different dimension of the result.

For example, the main comparison file in `data/qvm/backtest/experiments/experiment_comparison.csv` contains:

- `experiment`: variant name, such as "Quality Only Apr-01" or "QV Jan Rebalance"
- `scoring_mode`: the ranking mode used: `quality`, `valuation`, or `qv`
- `formation_month` / `formation_day`: the rebalance date used to form the portfolio
- `top_n`: number of names selected each year
- `years`: number of annual formation periods included in the run
- `cagr`: compound annual growth rate of the selected portfolio
- `sharpe`: annualized return over volatility, used to compare risk-adjusted performance
- `max_drawdown`: worst peak-to-trough decline experienced by the strategy
- `turnover`: average annual portfolio churn between hold periods
- `win_rate_vs_spy`: fraction of years where the portfolio beat SPY
- `spy_cagr`: benchmark CAGR for comparison
- `excess_cagr`: portfolio CAGR minus SPY CAGR

The backtest is therefore comparing not just raw return, but also how stable, concentrated, and benchmark-relative the strategy is.

## Quality metrics used in the score

The quality score is built from these individual metric families:

- `roic`: return on invested capital
- `roe`: return on equity
- `operating_margin`: operating profitability
- `revenue_cagr`: revenue growth rate
- `eps_cagr`: earnings-per-share growth rate
- `fcf_margin`: free cash flow margin
- `fcf_conversion`: free cash flow conversion efficiency
- `net_debt_ebitda`: balance-sheet leverage / net debt burden
- `leverage`: fallback leverage signal using interest coverage or debt/EBITDA

The effective-weight report shows which of these inputs are actually present in the company universe and how much each metric contributes after missing values are excluded from the weighting.

## Output conventions

The backtest workflow is intentionally simple and reproducible:

- all runs are annual
- universe is fixed for the formation year
- fundamentals are pulled from the prior-year dataset, not future data
- benchmark comparison is SPY over the same dates
- rank ordering is deterministic for the same data snapshot

## Typical workflow

For a standard research pass:

```bash
uv run qvm-quality-battletest --start-year 2015 --end-year 2025 --top-n 10
uv run qvm-quality-diagnostics --start-year 2015 --end-year 2025 --top-n 15
```

Then inspect the generated CSVs in `data/qvm/backtest/experiments` and compare the results before making a strategy decision.

## Related docs

- [business_overview.md](business_overview.md) — business criteria, scoring logic, and how the backtest is intended to be interpreted
- [../specifications/qvm_scoring.md](../specifications/qvm_scoring.md) — formula definitions and scoring rules
- [../qvm_backtesting_module_design.md](../qvm_backtesting_module_design.md) — implementation design notes
- [../qvm_backtesting_execution_checklist.md](../qvm_backtesting_execution_checklist.md) — execution plan and milestones
