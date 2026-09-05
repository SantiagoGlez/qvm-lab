import typer
import io
from contextlib import redirect_stdout

from quantlab.strategies.qvm.reports.console import print_report
from quantlab.strategies.qvm.reports.google_finance_chat import run_google_finance_audit
from quantlab.strategies.qvm.service import analyse_company

app = typer.Typer()


@app.command()
def main(
    ticker: str,
    google_finance_audit: bool = typer.Option(
        False,
        "--google-finance-audit",
        help="Append Google Finance beta chat QA response to the report.",
    ),
    google_finance_audit_mode: str = typer.Option(
        "quick",
        "--google-finance-audit-mode",
        help="Prompt mode for Google Finance QA: quick or full.",
    ),
    google_finance_timeout_seconds: int = typer.Option(
        120,
        "--google-finance-timeout-seconds",
        help="Timeout to wait for Google Finance chat response.",
    ),
    google_finance_show_browser: bool = typer.Option(
        False,
        "--google-finance-show-browser",
        help="Run automation in a visible browser window.",
    ),
):

    company = analyse_company(ticker)
    report_buffer = io.StringIO()
    with redirect_stdout(report_buffer):
        print_report(company)

    report_text = report_buffer.getvalue()
    print(report_text, end="")

    if google_finance_audit:
        print("Google Finance QA")
        print("-" * 30)
        print()
        audit_result = run_google_finance_audit(
            report_text,
            mode="full" if google_finance_audit_mode == "full" else "quick",
            timeout_seconds=google_finance_timeout_seconds,
            headless=not google_finance_show_browser,
        )
        if audit_result.success:
            print(audit_result.response)
        else:
            print("Google Finance audit was requested but could not be completed automatically.")
            print(f"Error: {audit_result.error}")
            print()
            print("No prompt/report dump was appended.")
            if "Playwright is not installed" in (audit_result.error or ""):
                print("To run automatic capture, install Playwright:")
                print("  uv add playwright")
                print("  uv run python -m playwright install chromium")
            else:
                print("Next checks:")
                print("  1) Try visible mode: --google-finance-show-browser")
                print("  2) Complete any consent/login challenge in the opened browser")
                print("  3) Re-run with a larger timeout (e.g. --google-finance-timeout-seconds 120)")
            print("Prompt templates are available in docs/specifications.")


if __name__ == "__main__":
    app()