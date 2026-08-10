import typer

from quantlab.strategies.qvm.reports.console import print_report
from quantlab.strategies.qvm.service import analyse_company

app = typer.Typer()


@app.command()
def company_cli(ticker: str):
    """Run QVM analysis for a single ticker and print the full report."""
    company = analyse_company(ticker)
    print_report(company)


@app.command()
def universe_cli():
    """Run the QVM universe analysis and write results to data/qvm/results.csv."""
    from scripts.strategies.qvm.update_universe import main as run_universe

    run_universe()


if __name__ == "__main__":
    app()
