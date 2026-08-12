from __future__ import annotations


def compute_cash_total(
    cash: float | None,
    short_term_investments: float | None = None,
) -> float | None:
    if cash is None and short_term_investments is None:
        return None
    return float(cash or 0.0) + float(short_term_investments or 0.0)


def compute_net_cash(
    total_debt: float | None,
    cash: float | None,
    short_term_investments: float | None = None,
) -> float | None:
    if total_debt is None:
        return None
    cash_total = compute_cash_total(cash, short_term_investments)
    if cash_total is None:
        return None
    return cash_total - float(total_debt)


def compute_net_debt_ebitda(
    total_debt: float | None,
    cash: float | None,
    ebitda: float | None,
    short_term_investments: float | None = None,
) -> float | None:
    if ebitda in (None, 0):
        return None
    net_cash = compute_net_cash(total_debt, cash, short_term_investments)
    if net_cash is None:
        return None
    return -net_cash / float(ebitda)


def compute_debt_to_ebitda(total_debt: float | None, ebitda: float | None) -> float | None:
    if total_debt is None or ebitda in (None, 0):
        return None
    return float(total_debt) / float(ebitda)


def compute_fcf_metrics(
    revenue: float | None,
    net_income: float | None,
    free_cash_flow: float | None = None,
    operating_cash_flow: float | None = None,
    capex: float | None = None,
) -> tuple[float | None, float | None, float | None]:
    fcf = None
    if free_cash_flow is not None:
        fcf = float(free_cash_flow)
    elif operating_cash_flow is not None and capex is not None:
        fcf = float(operating_cash_flow) - abs(float(capex))

    if fcf is None:
        return None, None, None

    fcf_margin = None
    if revenue not in (None, 0):
        fcf_margin = fcf / float(revenue)

    fcf_conversion = None
    if net_income not in (None, 0):
        fcf_conversion = fcf / float(net_income)

    return fcf, fcf_margin, fcf_conversion


def compute_tax_rate(
    tax_provision: float | None = None,
    pretax_income: float | None = None,
    effective_tax_rate: float | None = None,
) -> float | None:
    if tax_provision is not None and pretax_income not in (None, 0):
        return float(tax_provision) / float(pretax_income)
    if effective_tax_rate is not None:
        return float(effective_tax_rate)
    return None


def compute_invested_capital(
    total_debt: float | None,
    equity: float | None,
    cash: float | None,
    short_term_investments: float | None = None,
) -> float | None:
    if total_debt is None or equity is None:
        return None
    cash_total = compute_cash_total(cash, short_term_investments)
    if cash_total is None:
        return None
    return float(total_debt) + float(equity) - cash_total


def compute_roic(
    ebit: float | None,
    invested_capital: float | None,
    tax_rate: float | None = None,
    tax_provision: float | None = None,
    pretax_income: float | None = None,
    effective_tax_rate: float | None = None,
) -> float | None:
    if ebit is None:
        return None

    resolved_tax_rate = tax_rate
    if resolved_tax_rate is None:
        resolved_tax_rate = compute_tax_rate(
            tax_provision=tax_provision,
            pretax_income=pretax_income,
            effective_tax_rate=effective_tax_rate,
        )

    if resolved_tax_rate is None or invested_capital in (None, 0):
        return None

    nopat = float(ebit) * (1.0 - float(resolved_tax_rate))
    return nopat / float(invested_capital)
