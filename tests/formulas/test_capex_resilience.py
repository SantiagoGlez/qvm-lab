import pytest

from quantlab.strategies.qvm.intrinsic.capex_resilience import (
    CapexResilienceInputs,
    CapexResilienceService,
)


def test_resolve_free_cash_flow_handles_negative_capex_sign() -> None:
    assert CapexResilienceService.resolve_free_cash_flow(
        free_cash_flow=None,
        operating_cash_flow=40.0,
        capex=-10.0,
    ) == pytest.approx(30.0)


def test_analyse_returns_not_material_when_no_excess_capex() -> None:
    service = CapexResilienceService()
    inputs = CapexResilienceInputs(
        revenue=100.0,
        operating_cash_flow=30.0,
        capex=-8.0,
        free_cash_flow=22.0,
        net_cash=10.0,
        revenue_by_year={2020: 90.0, 2021: 92.0, 2022: 95.0, 2023: 97.0, 2024: 100.0},
        operating_cash_flow_by_year={},
        capex_by_year={2020: -7.0, 2021: -8.0, 2022: -7.5, 2023: -8.0, 2024: -8.0},
        free_cash_flow_by_year={},
    )

    result = service.analyse(inputs)

    assert result.relevance == "Not Material"
    assert result.excess_capex == pytest.approx(0.0)
    assert result.resilience == "Not Material"


def test_analyse_flags_unavailable_with_insufficient_history() -> None:
    service = CapexResilienceService()
    inputs = CapexResilienceInputs(
        revenue=100.0,
        operating_cash_flow=40.0,
        capex=-20.0,
        free_cash_flow=20.0,
        net_cash=5.0,
        revenue_by_year={2023: 95.0, 2024: 100.0},
        operating_cash_flow_by_year={},
        capex_by_year={2023: -10.0, 2024: -11.0},
        free_cash_flow_by_year={},
    )

    result = service.analyse(inputs)

    assert result.relevance == "High"
    assert result.historical_years_used == 0
    assert result.resilience == "Unavailable"


def test_analyse_classifies_high_resilience_for_strong_cushion() -> None:
    service = CapexResilienceService()
    inputs = CapexResilienceInputs(
        revenue=100.0,
        operating_cash_flow=45.0,
        capex=-18.0,
        free_cash_flow=27.0,
        net_cash=25.0,
        revenue_by_year={2020: 80.0, 2021: 84.0, 2022: 89.0, 2023: 94.0, 2024: 100.0},
        operating_cash_flow_by_year={},
        capex_by_year={2020: -8.0, 2021: -8.5, 2022: -9.0, 2023: -9.5, 2024: -10.0},
        free_cash_flow_by_year={},
    )

    result = service.analyse(inputs)

    assert result.relevance == "High"
    assert result.historical_capex_to_revenue_median == pytest.approx(0.1010638298)
    assert result.excess_capex == pytest.approx(7.89361702)
    assert result.stress_free_cash_flow == pytest.approx(19.10638298)
    assert result.resilience == "High"


def test_analyse_classifies_low_resilience_when_stress_erases_fcf() -> None:
    service = CapexResilienceService()
    inputs = CapexResilienceInputs(
        revenue=100.0,
        operating_cash_flow=22.0,
        capex=-20.0,
        free_cash_flow=2.0,
        net_cash=1.0,
        revenue_by_year={2020: 80.0, 2021: 85.0, 2022: 90.0, 2023: 95.0, 2024: 100.0},
        operating_cash_flow_by_year={},
        capex_by_year={2020: -8.0, 2021: -8.5, 2022: -9.0, 2023: -9.5, 2024: -10.0},
        free_cash_flow_by_year={},
    )

    result = service.analyse(inputs)

    assert result.relevance == "High"
    assert result.stress_free_cash_flow is not None
    assert result.stress_free_cash_flow < 0
    assert result.resilience == "Low"


def test_analyse_handles_negative_existing_fcf() -> None:
    service = CapexResilienceService()
    inputs = CapexResilienceInputs(
        revenue=100.0,
        operating_cash_flow=8.0,
        capex=-12.0,
        free_cash_flow=-4.0,
        net_cash=0.0,
        revenue_by_year={2020: 80.0, 2021: 84.0, 2022: 88.0, 2023: 94.0, 2024: 100.0},
        operating_cash_flow_by_year={},
        capex_by_year={2020: -6.0, 2021: -6.5, 2022: -7.0, 2023: -7.5, 2024: -8.0},
        free_cash_flow_by_year={},
    )

    result = service.analyse(inputs)

    assert result.current_free_cash_flow == pytest.approx(-4.0)
    assert result.stress_free_cash_flow is not None
    assert result.resilience == "Low"


def test_analyse_does_not_flag_routine_low_capex_business_on_cfo_ratio_alone() -> None:
    service = CapexResilienceService()
    inputs = CapexResilienceInputs(
        revenue=100.0,
        operating_cash_flow=4.8,
        capex=-2.0,
        free_cash_flow=2.8,
        net_cash=1.0,
        revenue_by_year={2020: 80.0, 2021: 85.0, 2022: 90.0, 2023: 95.0, 2024: 100.0},
        operating_cash_flow_by_year={},
        capex_by_year={2020: -1.4, 2021: -1.5, 2022: -1.6, 2023: -1.7, 2024: -1.8},
        free_cash_flow_by_year={},
    )

    result = service.analyse(inputs)

    assert result.capex_to_revenue == pytest.approx(0.02)
    assert result.capex_to_cfo == pytest.approx(0.4166666667)
    assert result.excess_capex_to_revenue == pytest.approx(0.0022222222)
    assert result.relevance == "Not Material"
    assert result.resilience == "Not Material"