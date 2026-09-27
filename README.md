# qvm-lab

Standalone repository for the QVM strategy (Quality, Valuation, Momentum).

This repo was split from a broader `quant-lab` workspace to keep QVM development isolated and easier to evolve.

## Included

- QVM core engine: `src/quantlab/strategies/qvm`
- QVM strategy scripts: `scripts/strategies/qvm`
- QVM scraping scripts:
  - `scripts/scrape_companiesmarketcap.py`
  - `scripts/scrape_companiesmarketcap_financials.py`
  - `scripts/scrape_stockanalysis.py`
- QVM scoring spec:
  - `docs/specifications/qvm_scoring.md`
- QVM data workspace:
  - `data/qvm/*`

## Prerequisites

Before running the QVM analysis scripts, make sure the required data files are available.
If the local dataset is missing or stale, run the scrapers first:

```bash
uv run python scripts/scrape_companiesmarketcap.py
uv run python scripts/scrape_companiesmarketcap_financials.py
```

These scripts populate the QVM data files under the `data/qvm` folder.

- Valuation history output: `data/qvm/companiesmarketcap/{ticker}_{slug}_valuation.csv`
- Financial metrics output: `data/qvm/companiesmarketcap/{ticker}_{slug}_financials.csv`

### Filing links and SEC probe pipeline

To build filing-link data used by the SEC companyfacts probe:

```bash
uv run python scripts/scrape_companiesmarketcap_filing_links.py
```

This now collects both `10k` and `annual-report` (AR) links by default. Use `--only-10k` to restrict collection.

To run the SEC probe with accession filtering from filing links:

```bash
uv run python scripts/probe_sec_companyfacts_metrics.py --all
```

By default the probe uses both `10k` and `annual-report` report types. You can override with `--report-types`, for example:

```bash
uv run python scripts/probe_sec_companyfacts_metrics.py --all --report-types 10k
```

## Business logic

The scoring rules and decision framework are documented in [docs/specifications/qvm_scoring.md](docs/specifications/qvm_scoring.md).

## Backtesting

The backtest workflow, commands, and experiment outputs are documented in [docs/backtest/README.md](docs/backtest/README.md).

For the business-facing explanation of how the backtest is designed and interpreted, see [docs/backtest/business_overview.md](docs/backtest/business_overview.md).

For portfolio correlation analysis, including external reference assets such as gold and US bonds, see [docs/qvm_portfolio_correlation.md](docs/qvm_portfolio_correlation.md).

For selection-level diagnostics (selected vs universe, valuation regime by year, and current-year diagnostics command), see [docs/backtest/qvm_selection_diagnostics.md](docs/backtest/qvm_selection_diagnostics.md).

For contribution-based tax-aware experiment variants (including soft-cap vs no-trim, turnover, and Spain capital-gains tax estimates with SPY baseline), see [docs/backtest/qvm_contribution_taxaware_experiments.md](docs/backtest/qvm_contribution_taxaware_experiments.md).

## Winner study (Top 20 period price winners)

This study isolates the 20 companies in the universe with the highest price appreciation across the backtest window and exports a yearly factor panel so we can inspect how price evolved together with:

- Quality score and quality subcomponents
- Historical valuation score/band
- Intrinsic valuation (Reverse DCF) metrics
- Momentum assessment and raw momentum indicators

Run:

```bash
uv run qvm-top-winners-evolution --start-year 2015 --end-year 2025 --top-n 20 --output-dir data/qvm/backtest/top_winners_evolution
```

Outputs:

- `data/qvm/backtest/top_winners_evolution/top_20_price_winners_summary.csv`
  - The selected top-20 winners with period buy/sell prices and full-period return.
- `data/qvm/backtest/top_winners_evolution/top_20_price_winners_yearly_panel.csv`
  - One row per ticker per formation year with price path, annual return, quality details, valuation fields, intrinsic fields, and momentum fields.

Interpretation note:

- This is a descriptive winner-cohort study (selected with full-period hindsight), useful for pattern discovery and UX/plot design.
- It should be followed by rolling/out-of-sample tests before drawing causal conclusions.

## Quick start

Install dependencies:

```bash
uv sync
```

Run a single-company analysis:

```bash
uv run qvm-company MSFT
```

Run a single-company analysis and append Google Finance beta chat QA at the end:

```bash
uv run qvm-company MSFT --google-finance-audit --google-finance-audit-mode quick
```

Available Google Finance QA flags for `qvm-company`:

- `--google-finance-audit`
- `--google-finance-audit-mode quick|full` (default: `quick`)
- `--google-finance-timeout-seconds <n>` (default: `120`)
- `--google-finance-show-browser` (runs browser in non-headless mode)

If automatic browser capture cannot run (for example Playwright missing, page structure changed, or auth challenge), the command still prints the full company report and then appends a paste-ready QA prompt.

Install optional browser automation dependencies for automatic capture:

```bash
uv add playwright
uv run python -m playwright install chromium
```

Standalone Google Finance QA helper from a saved report file:

```bash
uv run python scripts/strategies/qvm/google_finance_chat_audit.py --report-file data/qvm/sample_report.txt --mode quick
```

Prompt templates used by this integration live in:

- `docs/specifications/google_finance_report_audit_quick_prompt.md`
- `docs/specifications/google_finance_report_audit_full_prompt.md`

Run universe analysis (reads `data/qvm/companies.csv`, writes `data/qvm/results.csv`):

```bash
uv run qvm-universe
```

Audit a downloaded CompaniesMarketCap valuation file:

```bash
uv run python scripts/audit_marketcap.py RNO
```

Audit all valuation CSV files in the CompaniesMarketCap data directory and save the aggregated report to a file:

```bash
uv run python scripts/audit_marketcap.py --bulk --output data/qvm/companiesmarketcap_audit.txt
```

Audit a single CompaniesMarketCap historical financials CSV:

```bash
uv run python scripts/strategies/qvm/audit_historical_financials.py MSFT
```

Audit all historical financials CSV files in the universe (writes a report file by default):

```bash
uv run python scripts/strategies/qvm/audit_historical_financials.py --bulk
```

The single-ticker mode inspects the CSV file matching `data/qvm/companiesmarketcap/{ticker}_*_valuation.csv` and prints a concise report to the terminal. The bulk mode scans all valuation files in the directory, prints a summary to the terminal, and writes the same report content to the output file when `--output` is provided.

## Data quality — historical coverage

After downloading data for a new or updated universe, run the historical universe smoke test to validate and measure per-ticker quality metric coverage across the full backtest window (2015–2025):

```bash
uv run pytest tests/backtest/test_historical_universe_smoke.py -v
```

This test exercises the repository + adapter + scoring chain for every ticker in `data/qvm/companies.csv` and writes three coverage report files:

| File | Contents |
|---|---|
| `data/qvm/backtest/historical_coverage_by_company_summary.csv` | Per-ticker mean/min/max quality coverage across all formation years |
| `data/qvm/backtest/historical_coverage_by_year_summary.csv` | Per-year mean/min/max quality coverage across all tickers |
| `data/qvm/backtest/historical_coverage_by_year_company.csv` | Full detail: every ticker × year with scores and missing metrics |

Coverage is the fraction of the 9 quality dimensions populated for a given company/year snapshot. The production eligibility gate is `coverage >= 0.70` (7 of 9 metrics present). Tickers that consistently fall below this threshold across most years are unlikely to rank competitively and should be reviewed for removal from the universe.

Or run scripts directly:

```bash
uv run python scripts/strategies/qvm/update_company.py MSFT
uv run python scripts/strategies/qvm/update_universe.py
```

## Notes

- Dependencies were intentionally kept aligned with the original project for simplicity.
- You can slim dependencies later after validation.
