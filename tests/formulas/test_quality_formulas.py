import pytest

from quantlab.strategies.qvm.analysis.quality import (
    analyse_quality,
    quality_eligible,
    quality_metric_coverage,
    quality_missing_metrics,
)
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


def test_quality_normalizes_by_available_metrics() -> None:
    company = Company(
        ticker="TEST",
        metrics=CompanyMetrics(
            roic=0.20,
            roe=0.25,
            operating_margin=0.18,
        ),
    )

    result = analyse_quality(company)

    assert quality_metric_coverage(company) == pytest.approx(1 / 3)
    assert result.score > 80.0
    assert result.score < 100.0


def test_quality_requires_minimum_coverage_for_eligibility() -> None:
    company = Company(
        ticker="TEST",
        metrics=CompanyMetrics(
            roic=0.20,
        ),
    )

    assert quality_metric_coverage(company) == 1 / 9
    assert quality_eligible(company, minimum_coverage=0.7) is False
    assert quality_eligible(company, minimum_coverage=0.1) is True


def test_quality_exposes_coverage_and_missing_metrics() -> None:
    company = Company(
        ticker="TEST",
        metrics=CompanyMetrics(
            roic=0.20,
            roe=0.25,
            operating_margin=0.18,
        ),
    )

    result = analyse_quality(company)

    assert result.coverage == pytest.approx(1 / 3)
    assert result.missing_metrics == [
        "Revenue CAGR",
        "EPS CAGR",
        "FCF Margin",
        "FCF Conversion",
        "Net Debt/EBITDA",
        "Leverage",
    ]
    assert quality_missing_metrics(company) == result.missing_metrics
