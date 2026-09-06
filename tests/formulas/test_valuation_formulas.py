from quantlab.strategies.qvm.analysis.valuation import (
    analyse_valuation,
    compute_modern_regime_stats,
    get_valuation_band,
)
from quantlab.strategies.qvm.models import Company, CompanyMetrics


def test_valuation_band_thresholds_map_to_expected_labels() -> None:
    assert get_valuation_band(0.10) == "Deep Value"
    assert get_valuation_band(0.25) == "Cheap"
    assert get_valuation_band(0.55) == "Fair Value"
    assert get_valuation_band(0.79) == "Expensive"
    assert get_valuation_band(0.85) == "Very Expensive"


def test_valuation_formula_uses_percentile_discount_and_growth_components() -> None:
    company = Company(
        ticker="TEST",
        metrics=CompanyMetrics(forward_pe=10.0, trailing_pe=12.5),
    )
    company.valuation_facts.historical_average_pe = 20.0
    company.valuation_facts.historical_percentile = 0.0

    result = analyse_valuation(company)

    assert result.score == 87.5
    assert result.recommendation == "BUY"
    assert result.valuation_band == "Deep Value"


def test_missing_valuation_metrics_return_unknown_recommendation() -> None:
    company = Company(ticker="TEST")

    result = analyse_valuation(company)

    assert result.score == 0
    assert result.recommendation == "UNKNOWN"
    assert result.summary.startswith("Missing valuation information")


def test_discount_to_average_is_positive_when_current_pe_is_lower() -> None:
    company = Company(
        ticker="TEST",
        metrics=CompanyMetrics(forward_pe=20.0, trailing_pe=22.0),
    )
    company.valuation_facts.current_pe = 20.0
    company.valuation_facts.historical_average_pe = 25.0
    company.valuation_facts.historical_median_pe = 24.0
    company.valuation_facts.historical_percentile = 0.40

    analyse_valuation(company)

    assert company.valuation_facts.discount_to_average_pct == 20.0
    assert round(company.valuation_facts.discount_to_median_pct or 0.0, 4) == 16.6667


def test_modern_regime_stats_uses_recent_window() -> None:
    years, observations, median_pe, percentile = compute_modern_regime_stats(
        historical_pe_values=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0],
        current_pe=15.0,
    )

    assert years == 7
    assert observations == 7
    assert median_pe == 14.0
    assert percentile is not None
