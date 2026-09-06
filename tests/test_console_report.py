from quantlab.strategies.qvm.models import CapexResilienceAnalysis, Company
from quantlab.strategies.qvm.reports.console import print_report


def test_print_report_includes_capex_resilience_material_section(capsys) -> None:
    company = Company(ticker="TEST", name="Test Co")
    company.capex_resilience = CapexResilienceAnalysis(
        relevance="High",
        relevance_reason="capex/revenue is 18.0%; capex/CFO is 40.0%",
        capex_to_revenue=0.18,
        capex_to_cfo=0.40,
        fcf_margin=0.12,
        net_cash_to_capex=1.5,
        historical_capex_to_revenue_median=0.11,
        historical_years_used=5,
        excess_capex=7_000_000_000.0,
        stress_fcf_impact=-7_000_000_000.0,
        stress_free_cash_flow=12_000_000_000.0,
        stress_fcf_margin=0.08,
        resilience="Moderate",
    )

    print_report(company)
    output = capsys.readouterr().out

    assert "Capex Resilience" in output
    assert "Current Burden" in output
    assert "Historical Baseline" in output
    assert "Failed Incremental Capex" in output
    assert "Stress assumes capex above the historical normal level produces no incremental return." in output


def test_print_report_includes_capex_resilience_not_material_note(capsys) -> None:
    company = Company(ticker="TEST", name="Test Co")
    company.capex_resilience = CapexResilienceAnalysis(
        relevance="Not Material",
        relevance_reason="capex does not appear materially elevated versus current or historical burden",
        resilience="Not Material",
    )

    print_report(company)
    output = capsys.readouterr().out

    assert "Capex Resilience" in output
    assert "Relevance                Not Material" in output
    assert "Current Burden" not in output
    assert "capex does not appear materially elevated versus current or historical burden" in output