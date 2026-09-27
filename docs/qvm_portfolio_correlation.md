# QVM Portfolio Correlation Analysis

## Purpose

This analysis measures how the assets in a portfolio move relative to each other and relative to optional external reference assets such as gold or US bonds.

It is designed to answer questions like:

- Which holdings are moving together too closely?
- How diversified is the portfolio over time?
- Do external assets such as GLD or TLT reduce or increase the portfolio's correlation profile?

The implementation lives in [src/quantlab/strategies/qvm/analysis/correlation.py](../src/quantlab/strategies/qvm/analysis/correlation.py) and is exposed through the `qvm-correlation` CLI command.

## Core idea

Correlation is computed on returns, not raw prices.

That matters because price levels are not comparable across assets with different share prices. Daily or periodic returns show how each asset moves from one observation to the next, which is the correct basis for correlation.

The workflow is:

1. Load the portfolio tickers from a CSV file.
2. Optionally load extra reference assets from a second CSV file.
3. Fetch adjusted-close price history for every ticker.
4. Convert prices into return series using percent change.
5. Align all series on shared dates.
6. Compute the correlation matrix.
7. Export a matrix CSV, a summary CSV, and the portfolio return series.

## Data needed

### Portfolio file

The portfolio file is a CSV with at least one column:

- `ticker`

Optional columns:

- `weight` - used to build the portfolio return series when present

If `weight` is omitted, the analysis treats the portfolio holdings as equal weight.

Example:

```csv
ticker,weight
AAPL,0.25
MSFT,0.25
BRK,0.25
COST,0.25
```

Your existing `data/qvm/portfolio.csv` is valid even if it only contains tickers, because equal weights are used by default.

### Reference file

This is optional and can hold external assets that are not part of the portfolio but are useful for comparison, such as:

- `GLD` for gold
- `TLT` or `IEF` for US bonds
- `DXY` proxies if you want a dollar sensitivity check

Required column:

- `ticker`

Optional columns:

- `label` - friendly display name
- `weight` - if you want to assign custom weights in the summary logic

Example:

```csv
ticker,label,weight
GLD,Gold,1.0
TLT,US Bonds,1.0
```

## Timeframe

The current CLI defaults to a rolling **5-year lookback** using **daily adjusted-close prices**.

That means the calculation is based on the last five years of daily market data ending on the day you run the command.

You can change the window with:

- `--lookback-years <n>` on the CLI
- explicit `start` and `end` dates if you call the analysis function directly in code

## How the calculation works

The implementation uses adjusted close prices from the existing Yahoo price provider.

Adjusted close is important because it reflects splits and dividends, which makes the return series more accurate than using raw close prices.

For each ticker:

1. Fetch adjusted-close history.
2. Compute daily returns with `pct_change()`.
3. Align the series on the same trading dates.
4. Compute the correlation matrix on the aligned return frame.

For the portfolio series:

1. If weights exist in the portfolio CSV, use them.
2. Otherwise, normalize the holdings equally.
3. Combine the constituent return series into a single weighted portfolio return series.

## Outputs

The command writes three files to the output directory:

- `correlation_matrix.csv` - full correlation matrix for all portfolio and reference series
- `correlation_summary.csv` - one row per asset with correlation to the portfolio plus basic return stats
- `portfolio_returns.csv` - the aggregated portfolio return series used in the analysis

By default, outputs are written under:

```text
data/qvm/backtest/correlation/
```

## CLI usage

Run correlation analysis on the current portfolio file:

```bash
uv run qvm-correlation
```

Run correlation analysis with a custom reference file:

```bash
uv run qvm-correlation \
  --portfolio-file data/qvm/portfolio.csv \
  --reference-file data/qvm/reference_assets.csv \
  --lookback-years 5 \
  --output-dir data/qvm/backtest/correlation
```

## How to interpret it

- Correlation near `+1.0` means two assets tend to move together.
- Correlation near `0.0` means little linear relationship in the chosen window.
- Correlation near `-1.0` means the assets tend to move in opposite directions.

For diversification work, you usually care about the correlation of each holding versus the rest of the portfolio and versus external hedges such as gold or bonds.

## Practical notes

- This is a historical measure, not a forecast.
- Correlation depends on the chosen time window, so a 1-year window and a 5-year window can tell very different stories.
- Rolling correlation is a natural next extension if you want to see how relationships change through time.
- The analysis can fail for tickers with no available price history or incomplete data, and those assets are reported in the missing-assets list.

## Code entry points

- Analysis engine: [src/quantlab/strategies/qvm/analysis/correlation.py](../src/quantlab/strategies/qvm/analysis/correlation.py)
- CLI entry point: [src/qvm_lab/cli.py](../src/qvm_lab/cli.py)
- Console script: [pyproject.toml](../pyproject.toml)