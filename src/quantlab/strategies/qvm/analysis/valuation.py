from enum import Enum

from ..models import AnalysisResult, Company


class ValuationBand(str, Enum):
    DEEP_VALUE = "Deep Value"
    CHEAP = "Cheap"
    FAIR_VALUE = "Fair Value"
    EXPENSIVE = "Expensive"
    VERY_EXPENSIVE = "Very Expensive"


VALUATION_BANDS: list[tuple[float, ValuationBand]] = [
    (0.20, ValuationBand.DEEP_VALUE),
    (0.40, ValuationBand.CHEAP),
    (0.60, ValuationBand.FAIR_VALUE),
    (0.80, ValuationBand.EXPENSIVE),
    (1.00, ValuationBand.VERY_EXPENSIVE),
]


def get_valuation_band(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    for threshold, band in VALUATION_BANDS:
        if percentile < threshold or threshold == 1.0:
            return band.value
    return ValuationBand.VERY_EXPENSIVE.value


def analyse_valuation(company: Company) -> AnalysisResult:
    forward_pe = company.metrics.forward_pe
    trailing_pe = company.metrics.trailing_pe
    historical_pe_values = company.valuation_facts.historical_pe_values or []
    historical_average_pe = company.valuation_facts.historical_average_pe
    historical_median_pe = company.valuation_facts.historical_median_pe
    historical_percentile = company.valuation_facts.historical_percentile

    if not historical_pe_values and (forward_pe is None or trailing_pe is None):
        return AnalysisResult(
            score=0,
            summary="Missing valuation information",
            recommendation="UNKNOWN",
        )

    percentile_score = 0.0
    if historical_percentile is not None:
        percentile_score = max(0.0, 100.0 - (historical_percentile * 100.0))

    discount_score = 0.0
    if forward_pe is not None and historical_average_pe:
        discount_score = max(0.0, 100.0 - abs((forward_pe / historical_average_pe) - 1.0) * 100.0)
    elif forward_pe is not None and historical_median_pe:
        discount_score = max(0.0, 100.0 - abs((forward_pe / historical_median_pe) - 1.0) * 100.0)

    growth_score = 0.0
    if forward_pe is not None and trailing_pe is not None and trailing_pe > 0:
        ratio = forward_pe / trailing_pe
        if ratio <= 0.80:
            growth_score = 100
        elif ratio <= 0.90:
            growth_score = 90
        elif ratio <= 1.00:
            growth_score = 80
        elif ratio <= 1.10:
            growth_score = 70
        else:
            growth_score = 50

    score = round(
        percentile_score * 0.60
        + discount_score * 0.25
        + growth_score * 0.15,
        1,
    )

    discount_to_average_pct = None
    discount_to_median_pct = None
    if company.valuation_facts.current_pe is not None and historical_average_pe:
        discount_to_average_pct = (
            (company.valuation_facts.current_pe - historical_average_pe)
            / historical_average_pe
            * 100.0
        )
    if company.valuation_facts.current_pe is not None and historical_median_pe:
        discount_to_median_pct = (
            (company.valuation_facts.current_pe - historical_median_pe)
            / historical_median_pe
            * 100.0
        )

    company.valuation_facts.discount_to_average_pct = discount_to_average_pct
    company.valuation_facts.discount_to_median_pct = discount_to_median_pct

    valuation_band = get_valuation_band(historical_percentile)

    summary_parts = [
        f"Historical PE Percentile: {historical_percentile:.0%}" if historical_percentile is not None else "Historical PE Percentile: unavailable",
        f"Discount/Premium to Average PE: {forward_pe:.1f} vs {historical_average_pe:.1f}" if forward_pe is not None and historical_average_pe else "Discount/Premium to Average PE: unavailable",
        f"Forward PE vs Trailing PE: {forward_pe:.1f}/{trailing_pe:.1f}" if forward_pe is not None and trailing_pe is not None else "Forward PE vs Trailing PE: unavailable",
    ]

    return AnalysisResult(
        score=score,
        summary=" | ".join(summary_parts),
        recommendation="BUY" if score >= 80 else "WATCH",
        valuation_band=valuation_band,
    )