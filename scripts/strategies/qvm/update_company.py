import typer

from quantlab.strategies.qvm.reports.console import print_report
from quantlab.strategies.qvm.service import analyse_company

app = typer.Typer()


@app.command()
def main(ticker: str):

    company = analyse_company(ticker)

    print_report(company)


if __name__ == "__main__":
    app()