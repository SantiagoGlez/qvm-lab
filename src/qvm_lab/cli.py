import argparse
import runpy
import sys
from pathlib import Path

from quantlab.strategies.qvm.reports.console import print_report
from quantlab.strategies.qvm.service import analyse_company


def company_cli() -> None:
    """Run QVM analysis for a single ticker and print the full report."""
    parser = argparse.ArgumentParser(description="Run QVM analysis for one ticker")
    parser.add_argument("ticker", help="Ticker symbol to analyze")
    args = parser.parse_args(sys.argv[1:])

    company = analyse_company(args.ticker)
    print_report(company)


def universe_cli() -> None:
    """Run the QVM universe analysis and write results to data/qvm/results.csv."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "strategies" / "qvm" / "update_universe.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Universe script not found: {script_path}")

    sys.path.insert(0, str(repo_root))
    runpy.run_path(str(script_path), run_name="__main__")


if __name__ == "__main__":
    company_cli()
