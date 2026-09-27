# Quality-only strategy vs. SPY by valuation regime

This note correlates the annual valuation regime of the QVM universe with the annual performance of the quality-only strategy and the SPY benchmark.

## Source data

- Universe valuation regime: `data/qvm/backtest/selection_diagnostics/universe_valuation_regime_by_year.csv`
- Universe PE by year: `data/qvm/backtest/selection_diagnostics/universe_pe_by_year.csv`
- Quality-only annual returns: `data/qvm/backtest/quality_only_apr01_focus/returns.csv`
- Selection diagnostics: `data/qvm/backtest/quality_only_apr01_focus/selection_diagnostics.csv`
- Calculation script: `scripts/strategies/qvm/calculate_universe_pe_by_year.py`

The backtest benchmark in `returns.csv` is the SPY annual return used for comparison.

## Annual comparison table

| Year | Universe expensive share | Quality-only return | SPY return | Excess return |
|---|---:|---:|---:|---:|
| 2015 | 0.4819 | 0.1571 | 0.0274 | 0.1297 |
| 2016 | 0.6739 | 0.3074 | 0.1608 | 0.1466 |
| 2017 | 0.7957 | 0.5000 | 0.1150 | 0.3851 |
| 2018 | 0.5051 | 0.1294 | 0.1317 | -0.0023 |
| 2019 | 0.7981 | 0.0763 | -0.1212 | 0.1975 |
| 2020 | 0.8257 | 0.5879 | 0.6536 | -0.0657 |
| 2021 | 0.8073 | 0.1590 | 0.1455 | 0.0136 |
| 2022 | 0.6545 | -0.0352 | -0.0773 | 0.0421 |
| 2023 | 0.6216 | 0.5343 | 0.2890 | 0.2453 |
| 2024 | 0.6964 | 0.0514 | 0.0880 | -0.0366 |
| 2025 | 0.6818 | 0.2766 | 0.1814 | 0.0952 |
| Total | 0.6856 | 0.2495 | 0.1449 | 0.1046 |

> Total row is the average annual value across the 2015–2025 series for the last three return columns.

## Universe PE context and comparison table

The table below brings the repo-native universe PE metric and the external SPY market proxy into the same comparison frame so the valuation regime and annual return outcomes can be compared directly.

| Year | Universe expensive share | Universe PE median | SPY trailing 12M P/E (Jan 1) | Quality-only return | SPY return | Excess return |
|---|---:|---:|---:|---:|---:|---:|
| 2015 | 0.4819 | 18.80 | 20.02 | 0.1571 | 0.0274 | 0.1297 |
| 2016 | 0.6739 | 21.00 | 22.18 | 0.3074 | 0.1608 | 0.1466 |
| 2017 | 0.7957 | 26.30 | 23.59 | 0.5000 | 0.1150 | 0.3851 |
| 2018 | 0.5051 | 20.40 | 24.97 | 0.1294 | 0.1317 | -0.0023 |
| 2019 | 0.7981 | 25.65 | 19.60 | 0.0763 | -0.1212 | 0.1975 |
| 2020 | 0.8257 | 30.10 | 24.88 | 0.5879 | 0.6536 | -0.0657 |
| 2021 | 0.8073 | 32.80 | 35.96 | 0.1590 | 0.1455 | 0.0136 |
| 2022 | 0.6545 | 26.70 | 23.11 | -0.0352 | -0.0773 | 0.0421 |
| 2023 | 0.6216 | 29.40 | 22.82 | 0.5343 | 0.2890 | 0.2453 |
| 2024 | 0.6964 | 31.05 | 25.01 | 0.0514 | 0.0880 | -0.0366 |
| 2025 | 0.6818 | 30.70 | 28.16 | 0.2766 | 0.1814 | 0.0952 |
| Total | 0.6856 | 27.23 | 24.65 | 0.2495 | 0.1449 | 0.1046 |

> Universe PE is the median trailing P/E across the eligible QVM universe for that formation year. The SPY P/E is a separate external market benchmark from Google Finance, taken at the start of the calendar year and should be read as a broad-market context proxy rather than as an identical measurement.

> 2026 is shown in the external benchmark note but is excluded from the return comparison because the repository backtest return series ends at 2025.

## External SPY P/E benchmark (Google Finance proxy, market context only)

For reference, the benchmark proxy used for the market-regime view is:

| Year | SPY trailing 12M P/E (Jan 1) |
|---|---:|
| 2015 | 20.02 |
| 2016 | 22.18 |
| 2017 | 23.59 |
| 2018 | 24.97 |
| 2019 | 19.60 |
| 2020 | 24.88 |
| 2021 | 35.96 |
| 2022 | 23.11 |
| 2023 | 22.82 |
| 2024 | 25.01 |
| 2025 | 28.16 |
| 2026 | 27.98 |

This benchmark is directionally credible for a broad market regime view: it shows a very rich 2021 peak and a higher valuation regime around 2024–2026, which is consistent with the rising universe-level valuation regime we observed in the repo data.

## Interpretation

- The universe expensive share is the share of the eligible universe that falls into the Expensive or Very Expensive valuation bands.
- In the most expensive years (2017, 2019, 2020, 2021), the quality-only strategy still generated very strong absolute returns in 2017 and 2020, showing that quality selection can remain effective even when the opportunity set is rich.
- The strategy’s excess return was strongest in 2017, 2019, and 2023, which suggests the quality edge remains meaningful even when market context is not especially favorable.
- In years where the whole market was very stretched, such as 2020 and 2024, the strategy still held up in absolute terms but did not meaningfully outperform SPY on an excess basis.

## Correlation summary

Across 2015–2025:

- Correlation between universe expensive share and strategy return: about 0.293
- Correlation between universe expensive share and SPY return: about 0.254
- Correlation between universe expensive share and excess return: about 0.073

This means the universe’s valuation regime has some influence on absolute returns, but the quality-only strategy’s excess edge is not strongly explained by broad market expensiveness alone.

## Practical takeaway

The quality-only strategy is not merely a “buy when the market is cheap” strategy. It is a quality selection engine that still tends to add value in rich market periods, even if the market-wide opportunity set is expensive and the excess return can be muted in some years.
