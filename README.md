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

Or run scripts directly:

```bash
uv run python scripts/strategies/qvm/update_company.py MSFT
uv run python scripts/strategies/qvm/update_universe.py
```

## Notes

- Dependencies were intentionally kept aligned with the original project for simplicity.
- You can slim dependencies later after validation.
