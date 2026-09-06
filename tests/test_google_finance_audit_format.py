from quantlab.strategies.qvm.reports.google_finance_chat import format_google_finance_audit_response


def test_audit_formatter_prefixes_issue_categories() -> None:
    raw = """
Verdict: Pass with Caveats
Top 3 Data Issues
1. [Moderate] Missing leverage ratio detail; Evidence: "Debt/EBITDA 0.8x"; Why it matters: Completeness gap.
Top 3 Logic Gaps
1. [Minor] Sign convention wording is unclear; Evidence: "Discount to Average"; Why it matters: readability.
Confidence Score: 78
One-line Decision Safety: Safe to use
""".strip()

    formatted = format_google_finance_audit_response(raw)

    assert "[Presentation/Completeness]" in formatted
    assert "[Logic Error]" in formatted


def test_audit_formatter_does_not_hard_stop_isolated_cap_share_mismatch() -> None:
    raw = """
Verdict: Pass with Caveats
Top 3 Data Issues
1. [Critical] Implied Capitalization Discrepancy: market cap and shares disagree.; Evidence: "Market Cap 1571.2B" and "Shares Out 2.205B".; Why it matters: potential source mismatch.
Top 3 Logic Gaps
1. [Minor] None material; Evidence: "-"; Why it matters: evidence weak.
Confidence Score: 85
One-line Decision Safety: Not safe to use
""".strip()

    formatted = format_google_finance_audit_response(raw)

    assert "Decision Safety: Safe to use" in formatted
    assert "Safety Basis: cap/share mismatch isolated as data-integrity warning" in formatted
