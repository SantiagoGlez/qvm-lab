from __future__ import annotations

from typing import Any, Mapping

from ..metrics.core import compute_debt_to_ebitda, compute_fcf_metrics, compute_net_debt_ebitda
from ..models import Company


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number == float("nan"):
        return None
    return number


class HistoricalValuationAdapter:
    """Map historical valuation data to the production valuation model."""

    def adapt(self, ticker: str, payload: Mapping[str, Any]) -> Company:
        company = Company(ticker=ticker.upper())

        values = payload.get("historical_pe_values") or []
        historical_values = [float(value) for value in values if _as_float(value) is not None]

        current_pe = _as_float(payload.get("current_pe"))
        if current_pe is None and historical_values:
            current_pe = historical_values[-1]

        company.valuation_facts.historical_pe_values = historical_values or None
        company.valuation_facts.historical_average_pe = _as_float(payload.get("historical_average_pe"))
        company.valuation_facts.historical_median_pe = _as_float(payload.get("historical_median_pe"))
        company.valuation_facts.historical_percentile = _as_float(payload.get("historical_percentile"))
        company.valuation_facts.current_pe = current_pe
        company.valuation_facts.used_pe_count = int(payload.get("used_pe_count") or len(historical_values) or 0)

        # Preserve the same live-company contract used by valuation scoring.
        company.metrics.forward_pe = current_pe
        company.metrics.trailing_pe = current_pe

        if company.valuation_facts.historical_average_pe is None and historical_values:
            company.valuation_facts.historical_average_pe = sum(historical_values) / len(historical_values)
        if company.valuation_facts.historical_median_pe is None and historical_values:
            values_series = sorted(historical_values)
            midpoint = len(values_series) // 2
            if len(values_series) % 2 == 0:
                company.valuation_facts.historical_median_pe = (
                    values_series[midpoint - 1] + values_series[midpoint]
                ) / 2.0
            else:
                company.valuation_facts.historical_median_pe = values_series[midpoint]
        if company.valuation_facts.historical_percentile is None and historical_values and current_pe is not None:
            ordered = sorted(historical_values)
            rank = sum(1 for value in ordered if value <= current_pe)
            company.valuation_facts.historical_percentile = float((rank - 1) / max(len(ordered) - 1, 1))

        if company.valuation_facts.historical_pe_values and company.valuation_facts.current_pe is not None:
            company.valuation_facts.historical_pe_values = [
                float(value) for value in company.valuation_facts.historical_pe_values
            ]
            if company.valuation_facts.historical_pe_values[-1] != company.valuation_facts.current_pe:
                company.valuation_facts.historical_pe_values[-1] = company.valuation_facts.current_pe

        return company


class HistoricalQualityAdapter:
    """Map historical fundamentals to the production quality model."""

    def adapt(self, ticker: str, payload: Mapping[str, Any]) -> Company:
        company = Company(ticker=ticker.upper())
        metrics = company.metrics

        revenue = _as_float(payload.get("revenue"))
        net_income = _as_float(payload.get("net_income"))
        net_assets = _as_float(payload.get("net_assets"))
        roic = _as_float(payload.get("roic"))
        operating_margin = _as_float(payload.get("operating_margin"))
        total_debt = _as_float(payload.get("total_debt"))
        cash = _as_float(payload.get("cash"))
        operating_cash_flow = _as_float(payload.get("operating_cash_flow"))
        capex = _as_float(payload.get("capex"))
        free_cash_flow = _as_float(payload.get("free_cash_flow"))

        if net_income is not None and net_assets not in (None, 0):
            metrics.roe = net_income / net_assets
        if roic is not None:
            metrics.roic = roic
        if operating_margin is not None:
            metrics.operating_margin = operating_margin

        revenue_cagr = _as_float(payload.get("revenue_cagr"))
        eps_cagr = _as_float(payload.get("eps_cagr"))
        if revenue_cagr is not None:
            metrics.revenue_cagr = revenue_cagr
            metrics.revenue_cagr_years = int(payload.get("revenue_cagr_years") or 0) or None
        if eps_cagr is not None:
            metrics.eps_cagr = eps_cagr
            metrics.eps_cagr_years = int(payload.get("eps_cagr_years") or 0) or None

        _, fcf_margin, fcf_conversion = compute_fcf_metrics(
            revenue=revenue,
            net_income=net_income,
            free_cash_flow=free_cash_flow,
            operating_cash_flow=operating_cash_flow,
            capex=capex,
        )
        metrics.fcf_margin = fcf_margin
        metrics.fcf_conversion = fcf_conversion

        ebitda = None
        if revenue is not None and operating_margin is not None and operating_margin != 0:
            ebitda = revenue * operating_margin

        metrics.debt_to_ebitda = compute_debt_to_ebitda(total_debt=total_debt, ebitda=ebitda)
        metrics.net_debt_ebitda = compute_net_debt_ebitda(total_debt=total_debt, cash=cash, ebitda=ebitda)
        if metrics.net_debt_ebitda is None and total_debt is not None and cash is not None and ebitda in (None, 0):
            net_debt = total_debt - cash
            if net_debt != 0:
                metrics.net_debt_ebitda = float("inf") if net_debt > 0 else float("-inf")

        return company
