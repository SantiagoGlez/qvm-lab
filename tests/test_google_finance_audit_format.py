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


def test_audit_formatter_does_not_hard_stop_expected_unavailable_leverage() -> None:
    raw = """
Verdict: Pass with Caveats
Top 3 Data Issues
1. [Critical] Missing Leverage Metric: "Net Debt/EBITDA" missing due unavailable EBITDA.; Evidence: "Missing EPS CAGR, Net Debt/EBITDA".; Why it matters: leverage context incomplete.
Top 3 Logic Gaps
1. [Moderate] Cyclical earnings caveat.; Evidence: "Industry Auto Manufacturers".; Why it matters: PE interpretation is fragile.
Confidence Score: 82
One-line Decision Safety: Not safe to use
""".strip()

    formatted = format_google_finance_audit_response(raw)

    assert "Decision Safety: Safe to use" in formatted


def test_audit_formatter_does_not_hard_stop_missing_growth_windows_only() -> None:
    raw = """
Verdict: Pass with Caveats
Top 3 Data Issues
1. [Critical] Missing Core Growth Metrics: "EPS CAGR 5Y N/A" and "FCF CAGR 5Y N/A".; Evidence: "EPS CAGR 5Y N/A", "FCF CAGR 5Y N/A".; Why it matters: intrinsic coverage is incomplete.
Top 3 Logic Gaps
1. [Moderate] Business-type caveat.; Evidence: "Industry Auto Manufacturers".; Why it matters: cyclicality can distort PE signals.
Confidence Score: 75
One-line Decision Safety: Not safe to use
""".strip()

    formatted = format_google_finance_audit_response(raw)

    assert "Decision Safety: Safe to use" in formatted


def test_audit_formatter_normalizes_stylized_severity_and_splits_compound_lines() -> None:
    raw = """
Verdict: Fail
Material Data Issues
1. [Presentation/Completeness] 𝐶 𝑟 𝑖 𝑡 𝑖 𝑐 𝑎 𝑙 𝐶 𝑟 𝑖 𝑡 𝑖 𝑐 𝑎 𝑙 Missing Core Intrinsic Valuation Inputs.; Evidence: "Implied FCF Growth N/A".; Why it matters: missing core intrinsic output. 𝑀 𝑜 𝑑 𝑒 𝑟 𝑎 𝑡 𝑒 𝑀 𝑜 𝑑 𝑒 𝑟 𝑎 𝑡 𝑒 Missing Leverage Data.
Logic Gaps
1. [Logic Error] 𝐶 𝑟 𝑖 𝑡 𝑖 𝑐 𝑎 𝑙 𝐶 𝑟 𝑖 𝑡 𝑖 𝑐 𝑎 𝑙 Severe Math Sign and Percentage Error.; Evidence: "Relative to Average -132.3%".; Why it matters: sign interpretation unclear.
Confidence Score: 77
Decision Safety: Not safe to use
""".strip()

    formatted = format_google_finance_audit_response(raw)

    assert "Critical Critical" not in formatted
    assert "𝐶" not in formatted
    assert formatted.count("Material Data Issues") == 1
    assert "[Presentation/Completeness] [Presentation/Completeness]" not in formatted

    def test_audit_formatter_normalizes_bracketed_severity_style() -> None:
        raw = """
    Verdict: Pass with Caveats
    Top 3 Data Issues
    1. [Severity] Moderate: Missing core cash-flow metrics required for intrinsic valuation.; Evidence: "FCF CAGR 5Y N/A" and "FCF CAGR 10Y N/A".; Why it matters: intrinsic context is incomplete.
    Top 3 Logic Gaps
    1. [Severity] Moderate: Valuation sign convention error breaks historical baseline calculation math.; Evidence: "Relative to Average +6.3%" and "Sign Convention + = discount, - = premium".; Why it matters: directional interpretation could be wrong.
    Confidence Score: 75
    One-line Decision Safety: Not safe to use
    """.strip()

        formatted = format_google_finance_audit_response(raw)

        assert "Decision Safety: Safe to use" in formatted
        assert "[Presentation/Completeness] [Moderate]" in formatted
        assert "[Logic Error] [Moderate]" in formatted
