from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quantlab.strategies.qvm.analysis.quality import analyse_quality, quality_eligible
from quantlab.strategies.qvm.backtest.annual import score_universe_for_year
from quantlab.strategies.qvm.backtest.common import load_universe


DEFAULT_START_YEAR = 2015
DEFAULT_END_YEAR = 2026
DEFAULT_OUTPUT_PATH = Path("data/qvm/backtest/selection_diagnostics/universe_pe_by_year.csv")


def compute_universe_pe_by_year(start_year: int, end_year: int) -> list[dict[str, float | int]]:
    universe = load_universe()
    rows: list[dict[str, float | int]] = []

    for year in range(start_year, end_year + 1):
        companies = score_universe_for_year(year, universe)
        for company in companies:
            company.quality = analyse_quality(company)

        eligible = [company for company in companies if quality_eligible(company)]
        pe_values = [
            company.metrics.trailing_pe
            for company in eligible
            if company.metrics.trailing_pe is not None and company.metrics.trailing_pe > 0
        ]

        if not pe_values:
            rows.append(
                {
                    "formation_year": year,
                    "universe_n": len(eligible),
                    "universe_pe_median": None,
                    "universe_pe_mean": None,
                    "universe_pe_min": None,
                    "universe_pe_max": None,
                }
            )
            continue

        series = pd.Series(pe_values, dtype=float)
        rows.append(
            {
                "formation_year": year,
                "universe_n": len(eligible),
                "universe_pe_median": round(float(series.median()), 4),
                "universe_pe_mean": round(float(series.mean()), 4),
                "universe_pe_min": round(float(series.min()), 4),
                "universe_pe_max": round(float(series.max()), 4),
            }
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute yearly universe median/mean trailing PE across eligible QVM names.")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    rows = compute_universe_pe_by_year(args.start_year, args.end_year)
    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"Wrote universe PE table to {output_path}")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
