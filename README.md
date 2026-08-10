# qvm-lab

Standalone repository for the QVM strategy (Quality, Valuation, Momentum).

This repo was split from a broader `quant-lab` workspace to keep QVM development isolated and easier to evolve.

## Included

- QVM core engine: `src/quantlab/strategies/qvm`
- QVM strategy scripts: `scripts/strategies/qvm`
- QVM scraping scripts:
  - `scripts/scrape_companiesmarketcap.py`
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
```

These scripts populate the QVM data files under the `data/qvm` folder.

## Business logic

The scoring rules and decision framework are documented in [docs/specifications/qvm_scoring.md](docs/specifications/qvm_scoring.md).

## Quick start

Install dependencies:

```bash
uv sync
```

Run a single-company analysis:

```bash
uv run qvm-company MSFT
```

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

The single-ticker mode inspects the CSV file matching `data/qvm/companiesmarketcap/{ticker}_*_valuation.csv` and prints a concise report to the terminal. The bulk mode scans all valuation files in the directory, prints a summary to the terminal, and writes the same report content to the output file when `--output` is provided.

Or run scripts directly:

```bash
uv run python scripts/strategies/qvm/update_company.py MSFT
uv run python scripts/strategies/qvm/update_universe.py
```

## Notes

- Dependencies were intentionally kept aligned with the original project for simplicity.
- You can slim dependencies later after validation.
