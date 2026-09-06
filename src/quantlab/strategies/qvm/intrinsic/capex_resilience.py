from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..models import CapexResilienceAnalysis


@dataclass(slots=True)
class CapexResilienceInputs:
    revenue: float | None
    operating_cash_flow: float | None
    capex: float | None
    free_cash_flow: float | None
    net_cash: float | None

    revenue_by_year: dict[int, float]
    operating_cash_flow_by_year: dict[int, float]
    capex_by_year: dict[int, float]
    free_cash_flow_by_year: dict[int, float]

    revenue_source: str = "Unavailable"
    operating_cash_flow_source: str = "Unavailable"
    capex_source: str = "Unavailable"
    free_cash_flow_source: str = "Unavailable"
    history_source: str = "Unavailable"


class CapexResilienceService:
    def __init__(
        self,
        min_capex_to_revenue: float = 0.10,
        min_capex_to_cfo: float = 0.50,
        min_excess_capex_to_revenue: float = 0.03,
        preferred_history_years: int = 5,
        minimum_history_years: int = 3,
    ) -> None:
        self.min_capex_to_revenue = min_capex_to_revenue
        self.min_capex_to_cfo = min_capex_to_cfo
        self.min_excess_capex_to_revenue = min_excess_capex_to_revenue
        self.preferred_history_years = preferred_history_years
        self.minimum_history_years = minimum_history_years

    def analyse(self, inputs: CapexResilienceInputs) -> CapexResilienceAnalysis:
        current_fcf = self.resolve_free_cash_flow(
            free_cash_flow=inputs.free_cash_flow,
            operating_cash_flow=inputs.operating_cash_flow,
            capex=inputs.capex,
        )
        capex_to_revenue = self.safe_ratio(abs(inputs.capex) if inputs.capex is not None else None, inputs.revenue)
        capex_to_cfo = self.safe_ratio(abs(inputs.capex) if inputs.capex is not None else None, inputs.operating_cash_flow)
        fcf_margin = self.safe_ratio(current_fcf, inputs.revenue)
        net_cash_to_capex = self.safe_ratio(inputs.net_cash, abs(inputs.capex) if inputs.capex is not None else None)

        historical_intensities = self.historical_capex_to_revenue_series(
            revenue_by_year=inputs.revenue_by_year,
            capex_by_year=inputs.capex_by_year,
        )
        history_window = self.select_history_window(historical_intensities)
        historical_median = float(median(history_window)) if history_window else None
        historical_years_used = len(history_window)

        normal_capex = None
        excess_capex = None
        excess_capex_to_revenue = None
        if historical_median is not None and inputs.revenue not in (None, 0) and inputs.capex is not None:
            normal_capex = float(inputs.revenue) * historical_median
            excess_capex = max(0.0, abs(float(inputs.capex)) - normal_capex)
            excess_capex_to_revenue = self.safe_ratio(excess_capex, inputs.revenue)

        relevance, relevance_reason = self.classify_relevance(
            capex_to_revenue=capex_to_revenue,
            capex_to_cfo=capex_to_cfo,
            excess_capex_to_revenue=excess_capex_to_revenue,
            historical_years_used=historical_years_used,
        )

        stress_free_cash_flow = None
        stress_fcf_impact = None
        stress_fcf_impact_pct = None
        stress_fcf_margin = None
        if current_fcf is not None and excess_capex is not None:
            stress_free_cash_flow = current_fcf - excess_capex
            stress_fcf_impact = stress_free_cash_flow - current_fcf
            stress_fcf_impact_pct = self.safe_ratio(stress_fcf_impact, abs(current_fcf))
            stress_fcf_margin = self.safe_ratio(stress_free_cash_flow, inputs.revenue)

        resilience, resilience_reason = self.classify_resilience(
            relevance=relevance,
            current_free_cash_flow=current_fcf,
            stress_free_cash_flow=stress_free_cash_flow,
            stress_fcf_margin=stress_fcf_margin,
            stress_fcf_impact_pct=stress_fcf_impact_pct,
            capex_to_cfo=capex_to_cfo,
            net_cash_to_capex=net_cash_to_capex,
            historical_years_used=historical_years_used,
        )

        return CapexResilienceAnalysis(
            relevance=relevance,
            relevance_reason=relevance_reason,
            current_revenue=inputs.revenue,
            current_operating_cash_flow=inputs.operating_cash_flow,
            current_capex=inputs.capex,
            current_free_cash_flow=current_fcf,
            net_cash=inputs.net_cash,
            capex_to_revenue=capex_to_revenue,
            capex_to_cfo=capex_to_cfo,
            fcf_margin=fcf_margin,
            net_cash_to_capex=net_cash_to_capex,
            historical_capex_to_revenue_median=historical_median,
            historical_years_used=historical_years_used,
            excess_capex=excess_capex,
            excess_capex_to_revenue=excess_capex_to_revenue,
            stress_free_cash_flow=stress_free_cash_flow,
            stress_fcf_margin=stress_fcf_margin,
            stress_fcf_impact=stress_fcf_impact,
            stress_fcf_impact_pct=stress_fcf_impact_pct,
            resilience=resilience,
            resilience_reason=resilience_reason,
            operating_cash_flow_source=inputs.operating_cash_flow_source,
            capex_source=inputs.capex_source,
            revenue_source=inputs.revenue_source,
            history_source=inputs.history_source,
        )

    @staticmethod
    def resolve_free_cash_flow(
        free_cash_flow: float | None,
        operating_cash_flow: float | None,
        capex: float | None,
    ) -> float | None:
        if free_cash_flow is not None:
            return float(free_cash_flow)
        if operating_cash_flow is None or capex is None:
            return None
        return float(operating_cash_flow) - abs(float(capex))

    @staticmethod
    def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None
        return float(numerator) / float(denominator)

    @staticmethod
    def historical_capex_to_revenue_series(
        revenue_by_year: dict[int, float],
        capex_by_year: dict[int, float],
    ) -> list[float]:
        years = sorted(set(revenue_by_year).intersection(capex_by_year))
        intensities: list[float] = []
        for year in years:
            revenue = revenue_by_year.get(year)
            capex = capex_by_year.get(year)
            if revenue in (None, 0) or capex is None:
                continue
            intensities.append(abs(float(capex)) / float(revenue))
        return intensities

    def select_history_window(self, historical_intensities: list[float]) -> list[float]:
        if len(historical_intensities) >= self.preferred_history_years:
            return historical_intensities[-self.preferred_history_years :]
        if len(historical_intensities) >= self.minimum_history_years:
            return historical_intensities
        return []

    def classify_relevance(
        self,
        *,
        capex_to_revenue: float | None,
        capex_to_cfo: float | None,
        excess_capex_to_revenue: float | None,
        historical_years_used: int,
    ) -> tuple[str, str | None]:
        reasons: list[str] = []
        if capex_to_revenue is not None and capex_to_revenue >= self.min_capex_to_revenue:
            reasons.append(
                f"capex/revenue is {capex_to_revenue:.1%}"
            )
        if capex_to_cfo is not None and capex_to_cfo >= self.min_capex_to_cfo:
            reasons.append(
                f"capex/CFO is {capex_to_cfo:.1%}"
            )
        if excess_capex_to_revenue is not None and excess_capex_to_revenue >= self.min_excess_capex_to_revenue:
            reasons.append(
                f"excess capex/revenue is {excess_capex_to_revenue:.1%} above normal"
            )

        if reasons:
            return "High", "; ".join(reasons)
        if historical_years_used == 0 and capex_to_revenue is None and capex_to_cfo is None:
            return "Unavailable", "missing current capex burden inputs"
        if historical_years_used < self.minimum_history_years:
            return "Not Material", "capex does not screen as elevated and historical baseline is limited"
        return "Not Material", "capex does not appear materially elevated versus current or historical burden"

    @staticmethod
    def classify_resilience(
        *,
        relevance: str,
        current_free_cash_flow: float | None,
        stress_free_cash_flow: float | None,
        stress_fcf_margin: float | None,
        stress_fcf_impact_pct: float | None,
        capex_to_cfo: float | None,
        net_cash_to_capex: float | None,
        historical_years_used: int,
    ) -> tuple[str, str | None]:
        if relevance == "Unavailable":
            return "Unavailable", "insufficient inputs to assess capex resilience"
        if relevance == "Not Material":
            return "Not Material", "current capex cycle does not appear materially elevated"
        if current_free_cash_flow is None or stress_free_cash_flow is None:
            return "Unavailable", "missing free cash flow inputs for stress test"
        if historical_years_used < 3:
            return "Unavailable", "insufficient history for normal capex baseline"
        if stress_free_cash_flow <= 0:
            return "Low", "stress case drives free cash flow to zero or below"
        if stress_fcf_margin is not None and stress_fcf_margin < 0.05:
            return "Low", "stress free cash flow margin becomes thin"

        stress_drawdown = abs(stress_fcf_impact_pct) if stress_fcf_impact_pct is not None else None
        strong_balance_sheet = net_cash_to_capex is not None and net_cash_to_capex >= 1.0
        high_burden = capex_to_cfo is not None and capex_to_cfo >= 0.75

        if stress_fcf_margin is not None and stress_fcf_margin >= 0.10 and (
            (stress_drawdown is not None and stress_drawdown <= 0.25)
            or (strong_balance_sheet and stress_drawdown is not None and stress_drawdown <= 0.35)
        ):
            return "High", "stress leaves substantial positive free cash flow"

        if high_burden and not strong_balance_sheet:
            return "Low", "capex already consumes most operating cash with limited balance-sheet cushion"

        return "Moderate", "stress leaves positive free cash flow but with meaningful compression"