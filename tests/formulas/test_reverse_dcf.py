from quantlab.strategies.qvm.intrinsic.reverse_dcf import ReverseDCFInputs, ReverseDCFService


def test_reverse_dcf_solver_recovers_known_growth_rate() -> None:
    service = ReverseDCFService(discount_rate=0.09, terminal_growth=0.03, projection_years=10)

    true_growth = 0.12
    ttm_fcf_per_share = 3.0
    target_price = service.present_value_per_share(
        ttm_fcf_per_share=ttm_fcf_per_share,
        growth=true_growth,
        discount_rate=0.09,
        terminal_growth=0.03,
        projection_years=10,
    )
    assert target_price is not None

    implied = service.solve_implied_growth(
        current_share_price=target_price,
        ttm_fcf_per_share=ttm_fcf_per_share,
        discount_rate=0.09,
        terminal_growth=0.03,
        projection_years=10,
    )

    assert implied is not None
    assert abs(implied - true_growth) < 1e-5


def test_compute_cagr_handles_invalid_inputs() -> None:
    assert ReverseDCFService.compute_cagr(start_value=None, end_value=10.0, years=5) is None
    assert ReverseDCFService.compute_cagr(start_value=10.0, end_value=None, years=5) is None
    assert ReverseDCFService.compute_cagr(start_value=-10.0, end_value=20.0, years=5) is None
    assert ReverseDCFService.compute_cagr(start_value=10.0, end_value=-20.0, years=5) is None
    assert ReverseDCFService.compute_cagr(start_value=10.0, end_value=20.0, years=0) is None


def test_representative_growth_uses_median_of_available_values() -> None:
    value = ReverseDCFService.representative_growth(
        [0.10, None, 0.20, 0.30, None, 0.50],
        apply_cap=False,
    )
    assert value == 0.25


def test_representative_growth_can_apply_winsorization_caps() -> None:
    capped = ReverseDCFService.representative_growth(
        [0.10, 0.20, 0.60],
        cap_floor=-0.15,
        cap_ceiling=0.25,
        apply_cap=True,
    )
    uncapped = ReverseDCFService.representative_growth(
        [0.10, 0.20, 0.60],
        apply_cap=False,
    )

    assert capped == 0.20
    assert uncapped == 0.20


def test_representative_growth_caps_extreme_median_when_needed() -> None:
    capped = ReverseDCFService.representative_growth(
        [0.30, 0.40, 0.60],
        cap_floor=-0.15,
        cap_ceiling=0.25,
        apply_cap=True,
    )
    uncapped = ReverseDCFService.representative_growth(
        [0.30, 0.40, 0.60],
        apply_cap=False,
    )

    assert capped == 0.25
    assert uncapped == 0.40


def test_expectation_gap_and_assessment_thresholds() -> None:
    assert ReverseDCFService.expectation_gap(0.12, 0.06) == 0.06
    assert ReverseDCFService.classify_assessment(0.06) == "Very Conservative Expectations"
    assert ReverseDCFService.classify_assessment(0.03) == "Conservative Expectations"
    assert ReverseDCFService.classify_assessment(0.00) == "Reasonable Expectations"
    assert ReverseDCFService.classify_assessment(-0.03) == "Reasonable Expectations"
    assert ReverseDCFService.classify_assessment(-0.04) == "Optimistic Expectations"
    assert ReverseDCFService.classify_assessment(-0.07) == "Very Optimistic Expectations"


def test_analysis_uses_available_growth_inputs_only() -> None:
    service = ReverseDCFService(discount_rate=0.09, terminal_growth=0.03, projection_years=10)

    inputs = ReverseDCFInputs(
        current_share_price=50.0,
        shares_outstanding=100.0,
        market_cap=5000.0,
        ttm_free_cash_flow=400.0,
        revenue_by_year={2015: 100.0, 2020: 150.0, 2025: 220.0},
        eps_by_year={2020: 5.0, 2025: 10.0},
        fcf_by_year={2020: 30.0, 2025: 60.0},
        revenue_source="CompaniesMarketCap Financials",
        eps_source="CompaniesMarketCap Financials",
        fcf_source="SEC CompanyFacts",
    )

    result = service.analyse(inputs)

    assert result.implied_growth is not None
    assert result.revenue_cagr_5y is not None
    assert result.revenue_cagr_10y is not None
    assert result.eps_cagr_5y is not None
    assert result.eps_cagr_10y is None
    assert result.fcf_cagr_5y is not None
    assert result.fcf_cagr_10y is None
    assert result.historical_growth_estimate is not None
    assert result.representative_growth_uses_cap is True
    assert result.history_quality in {"Stable", "Moderate", "Volatile", "Limited"}
    assert result.revenue_growth_source == "CompaniesMarketCap Financials"
    assert result.eps_growth_source == "CompaniesMarketCap Financials"
    assert result.fcf_growth_source == "SEC CompanyFacts"
