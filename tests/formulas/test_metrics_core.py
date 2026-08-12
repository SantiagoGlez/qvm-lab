import pytest

from quantlab.strategies.qvm.metrics.core import (
    compute_cash_total,
    compute_debt_to_ebitda,
    compute_fcf_metrics,
    compute_invested_capital,
    compute_net_cash,
    compute_net_debt_ebitda,
    compute_roic,
    compute_tax_rate,
)


def test_compute_fcf_metrics_from_operating_cash_flow_and_capex() -> None:
    fcf, fcf_margin, fcf_conversion = compute_fcf_metrics(
        revenue=100.0,
        net_income=20.0,
        operating_cash_flow=40.0,
        capex=-10.0,
    )

    assert fcf == pytest.approx(30.0)
    assert fcf_margin == pytest.approx(0.30)
    assert fcf_conversion == pytest.approx(1.5)


def test_compute_tax_rate_fallback_to_effective_rate() -> None:
    assert compute_tax_rate(tax_provision=None, pretax_income=None, effective_tax_rate=0.21) == pytest.approx(0.21)


def test_compute_roic_from_inputs() -> None:
    invested_capital = compute_invested_capital(total_debt=30.0, equity=70.0, cash=10.0, short_term_investments=5.0)
    assert invested_capital == pytest.approx(85.0)

    roic = compute_roic(ebit=25.0, invested_capital=invested_capital, tax_rate=0.2)
    assert roic == pytest.approx((25.0 * 0.8) / 85.0)


def test_compute_leverage_ratios() -> None:
    assert compute_cash_total(10.0, 5.0) == pytest.approx(15.0)
    assert compute_net_cash(total_debt=30.0, cash=10.0, short_term_investments=5.0) == pytest.approx(-15.0)
    assert compute_debt_to_ebitda(total_debt=30.0, ebitda=10.0) == pytest.approx(3.0)
    assert compute_net_debt_ebitda(total_debt=30.0, cash=10.0, short_term_investments=5.0, ebitda=10.0) == pytest.approx(1.5)
