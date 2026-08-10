from quantlab.strategies.qvm.analysis.quality import analyse_quality
from quantlab.strategies.qvm.models import Company, CompanyMetrics


def test_quality_scoring_uses_thresholds_for_key_metrics() -> None:
    company = Company(
        ticker="TEST",
        metrics=CompanyMetrics(
            roic=0.20,
            roe=0.25,
            operating_margin=0.18,
            revenue_cagr=0.12,
            eps_cagr=0.16,
            fcf_margin=0.08,
            fcf_conversion=0.75,
            net_debt_ebitda=0.2,
            interest_coverage=8.0,
        ),
    )

    result = analyse_quality(company)

    assert result.score > 75.0
    assert result.recommendation == "Good"


def test_quality_scores_missing_values_as_zero() -> None:
    company = Company(ticker="TEST")

    result = analyse_quality(company)

    assert result.score == 0.0
    assert result.recommendation == "Weak"
