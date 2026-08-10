from quantlab.strategies.qvm.analysis.valuation import analyse_valuation, get_valuation_band
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
