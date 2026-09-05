from __future__ import annotations

from pathlib import Path

import typer

from quantlab.strategies.qvm.reports.google_finance_chat import run_google_finance_audit

app = typer.Typer(help="Google Finance beta chat audit helper for QVM reports.")


@app.command()
def main(
    report_file: Path = typer.Option(..., "--report-file", exists=True, readable=True),
    mode: str = typer.Option("quick", "--mode", help="Audit mode: quick or full."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", help="Chat response timeout."),
    show_browser: bool = typer.Option(False, "--show-browser", help="Run with visible browser."),
) -> None:
    report_text = report_file.read_text(encoding="utf-8")
    audit_result = run_google_finance_audit(
        report_text,
        mode="full" if mode == "full" else "quick",
        timeout_seconds=timeout_seconds,
        headless=not show_browser,
    )

    if audit_result.success:
        print(audit_result.response)
        return

    print("Google Finance audit failed.")
    print(f"Error: {audit_result.error}")
    print()
    print("Prompt ready to paste:")
    print(audit_result.prompt)


if __name__ == "__main__":
    app()
