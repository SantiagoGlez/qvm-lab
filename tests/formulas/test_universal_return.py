from quantlab.strategies.qvm.analysis.universal_return import (
    UniversalReturnInputs,
    _normalize_fraction,
    calculate_universal_return,
)


def test_universal_return_happy_path() -> None:
    inputs = UniversalReturnInputs(
        ticker="TEST",
        price_current=100.0,
        eps_ttm=5.0,
        pe_current=20.0,
        pe_historical_median=25.0,
        dividend_yield=0.02,
        buyback_rate=0.03,
        roe_ttm=0.15,
        retention_rate=0.6,
        revenue_cagr_10y=0.08,
    )

    result = calculate_universal_return(inputs, horizon_years=5)

    assert result.line_1_capital_yield is not None
    assert abs(result.line_1_capital_yield - 0.05) < 1e-9
    assert result.line_2_fundamental_growth is not None
    assert abs(result.line_2_fundamental_growth - 0.09) < 1e-9
    assert result.line_3_valuation_delta is not None
    assert result.line_3_valuation_delta > 0
    assert result.expected_annual_return is not None
    assert result.expected_annual_return > result.line_1_capital_yield
    assert result.confidence_label == "High"
    assert result.missing_inputs == []


def test_growth_guardrail_uses_revenue_cagr_for_outlier() -> None:
    inputs = UniversalReturnInputs(
        ticker="TEST",
        price_current=100.0,
        eps_ttm=5.0,
        pe_current=20.0,
        pe_historical_median=20.0,
        dividend_yield=0.01,
        buyback_rate=0.0,
        roe_ttm=0.50,
        retention_rate=0.8,
        revenue_cagr_10y=0.07,
    )

    result = calculate_universal_return(inputs, horizon_years=5)

    assert result.line_2_fundamental_growth == 0.07
    assert any("outlier" in note.lower() for note in result.assumptions)
    assert result.confidence_label in {"Medium", "Low"}


def test_pe_guardrail_replaces_extreme_current_pe() -> None:
    inputs = UniversalReturnInputs(
        ticker="TEST",
        price_current=100.0,
        eps_ttm=2.0,
        pe_current=80.0,
        pe_historical_median=20.0,
        dividend_yield=0.0,
        buyback_rate=0.0,
        roe_ttm=0.12,
        retention_rate=0.7,
        revenue_cagr_10y=0.06,
    )

    result = calculate_universal_return(inputs, horizon_years=5)

    assert result.pe_current_effective == 20.0
    assert result.line_3_valuation_delta == 0.0
    assert any("above 50" in note.lower() for note in result.assumptions)


def test_missing_inputs_are_listed_and_labeled() -> None:
    inputs = UniversalReturnInputs(
        ticker="TEST",
        price_current=100.0,
        eps_ttm=5.0,
        pe_current=20.0,
        pe_historical_median=25.0,
        dividend_yield=0.02,
        buyback_rate=None,
        roe_ttm=None,
        retention_rate=None,
        revenue_cagr_10y=None,
    )

    result = calculate_universal_return(inputs, horizon_years=5)

    assert result.confidence_label == "Low"
    assert "buyback_rate" in result.missing_inputs
    assert "roe_ttm" in result.missing_inputs
    assert "retention_rate" in result.missing_inputs
    assert "revenue_cagr_10y" in result.missing_inputs


def test_normalize_fraction_handles_percent_style_values() -> None:
    assert abs(_normalize_fraction(6.44) - 0.0644) < 1e-12
    assert abs(_normalize_fraction(0.94) - 0.0094) < 1e-12
