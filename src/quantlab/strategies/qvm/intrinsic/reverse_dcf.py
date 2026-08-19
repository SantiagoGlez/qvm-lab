from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..models import ReverseDCFAnalysis


@dataclass(slots=True)
class ReverseDCFInputs:
    current_share_price: float | None
    shares_outstanding: float | None
    market_cap: float | None
    ttm_free_cash_flow: float | None

    revenue_by_year: dict[int, float]
    eps_by_year: dict[int, float]
    fcf_by_year: dict[int, float]

    revenue_source: str = "Unavailable"
    eps_source: str = "Unavailable"
    fcf_source: str = "Unavailable"


class ReverseDCFService:
    def __init__(
        self,
        discount_rate: float = 0.09,
        terminal_growth: float = 0.03,
        projection_years: int = 10,
        representative_growth_cap_floor: float = -0.15,
        representative_growth_cap_ceiling: float = 0.25,
        enable_representative_growth_cap: bool = True,
    ) -> None:
        self.discount_rate = discount_rate
        self.terminal_growth = terminal_growth
        self.projection_years = projection_years
        self.representative_growth_cap_floor = representative_growth_cap_floor
        self.representative_growth_cap_ceiling = representative_growth_cap_ceiling
        self.enable_representative_growth_cap = enable_representative_growth_cap

    def analyse(self, inputs: ReverseDCFInputs) -> ReverseDCFAnalysis:
        fcf_per_share = self._fcf_per_share(
            ttm_free_cash_flow=inputs.ttm_free_cash_flow,
            shares_outstanding=inputs.shares_outstanding,
            market_cap=inputs.market_cap,
            current_share_price=inputs.current_share_price,
        )

        implied_growth = self.solve_implied_growth(
            current_share_price=inputs.current_share_price,
            ttm_fcf_per_share=fcf_per_share,
            discount_rate=self.discount_rate,
            terminal_growth=self.terminal_growth,
            projection_years=self.projection_years,
        )

        revenue_cagr_5y = self.compute_window_cagr(inputs.revenue_by_year, 5)
        revenue_cagr_10y = self.compute_window_cagr(inputs.revenue_by_year, 10)

        eps_cagr_5y = self.compute_window_cagr(inputs.eps_by_year, 5)
        eps_cagr_10y = self.compute_window_cagr(inputs.eps_by_year, 10)

        fcf_cagr_5y = self.compute_window_cagr(inputs.fcf_by_year, 5)
        fcf_cagr_10y = self.compute_window_cagr(inputs.fcf_by_year, 10)

        growth_candidates = [
            fcf_cagr_5y,
            fcf_cagr_10y,
            eps_cagr_5y,
            eps_cagr_10y,
            revenue_cagr_5y,
            revenue_cagr_10y,
        ]

        historical_growth_estimate_raw = self.representative_growth(growth_candidates)
        historical_growth_estimate = self.representative_growth(
            growth_candidates,
            cap_floor=self.representative_growth_cap_floor,
            cap_ceiling=self.representative_growth_cap_ceiling,
            apply_cap=self.enable_representative_growth_cap,
        )

        expectation_gap = self.expectation_gap(historical_growth_estimate, implied_growth)
        assessment = self.classify_assessment(expectation_gap)
        growth_input_count = len([value for value in growth_candidates if value is not None])
        growth_dispersion = self.growth_dispersion(growth_candidates)
        history_quality = self.classify_history_quality(growth_dispersion, growth_input_count)

        return ReverseDCFAnalysis(
            implied_growth=implied_growth,
            discount_rate=self.discount_rate,
            terminal_growth=self.terminal_growth,
            projection_years=self.projection_years,
            revenue_cagr_5y=revenue_cagr_5y,
            revenue_cagr_10y=revenue_cagr_10y,
            eps_cagr_5y=eps_cagr_5y,
            eps_cagr_10y=eps_cagr_10y,
            fcf_cagr_5y=fcf_cagr_5y,
            fcf_cagr_10y=fcf_cagr_10y,
            historical_growth_estimate=historical_growth_estimate,
            historical_growth_estimate_raw=historical_growth_estimate_raw,
            representative_growth_uses_cap=self.enable_representative_growth_cap,
            representative_growth_cap_floor=self.representative_growth_cap_floor,
            representative_growth_cap_ceiling=self.representative_growth_cap_ceiling,
            growth_input_count=growth_input_count,
            growth_dispersion=growth_dispersion,
            history_quality=history_quality,
            revenue_growth_source=inputs.revenue_source,
            eps_growth_source=inputs.eps_source,
            fcf_growth_source=inputs.fcf_source,
            expectation_gap=expectation_gap,
            assessment=assessment,
        )

    @staticmethod
    def _fcf_per_share(
        ttm_free_cash_flow: float | None,
        shares_outstanding: float | None,
        market_cap: float | None,
        current_share_price: float | None,
    ) -> float | None:
        if ttm_free_cash_flow is None:
            return None
        if shares_outstanding is not None and shares_outstanding > 0:
            return ttm_free_cash_flow / shares_outstanding
        if market_cap is not None and current_share_price is not None and current_share_price > 0:
            inferred_shares = market_cap / current_share_price
            if inferred_shares > 0:
                return ttm_free_cash_flow / inferred_shares
        return None

    @staticmethod
    def present_value_per_share(
        ttm_fcf_per_share: float,
        growth: float,
        discount_rate: float,
        terminal_growth: float,
        projection_years: int,
    ) -> float | None:
        if projection_years <= 0:
            return None
        if discount_rate <= terminal_growth:
            return None
        if ttm_fcf_per_share <= 0:
            return None
        if growth <= -1.0:
            return None

        pv = 0.0
        for year in range(1, projection_years + 1):
            fcf_year = ttm_fcf_per_share * ((1.0 + growth) ** year)
            if fcf_year <= 0:
                return None
            pv += fcf_year / ((1.0 + discount_rate) ** year)

        terminal_fcf = ttm_fcf_per_share * ((1.0 + growth) ** projection_years)
        terminal_value = terminal_fcf * (1.0 + terminal_growth) / (discount_rate - terminal_growth)
        pv += terminal_value / ((1.0 + discount_rate) ** projection_years)

        return pv

    @classmethod
    def solve_implied_growth(
        cls,
        current_share_price: float | None,
        ttm_fcf_per_share: float | None,
        discount_rate: float,
        terminal_growth: float,
        projection_years: int,
    ) -> float | None:
        if current_share_price is None or current_share_price <= 0:
            return None
        if ttm_fcf_per_share is None or ttm_fcf_per_share <= 0:
            return None

        def objective(growth: float) -> float | None:
            pv = cls.present_value_per_share(
                ttm_fcf_per_share=ttm_fcf_per_share,
                growth=growth,
                discount_rate=discount_rate,
                terminal_growth=terminal_growth,
                projection_years=projection_years,
            )
            if pv is None:
                return None
            return pv - current_share_price

        low = -0.90
        high = 0.60

        f_low = objective(low)
        f_high = objective(high)
        if f_low is None or f_high is None:
            return None

        expansions = 0
        while f_low * f_high > 0 and expansions < 10:
            high += 0.40
            f_high = objective(high)
            if f_high is None:
                return None
            expansions += 1

        if f_low * f_high > 0:
            return None

        for _ in range(80):
            mid = (low + high) / 2.0
            f_mid = objective(mid)
            if f_mid is None:
                return None
            if abs(f_mid) < 1e-6:
                return mid
            if f_low * f_mid <= 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid

        return (low + high) / 2.0

    @staticmethod
    def compute_cagr(start_value: float | None, end_value: float | None, years: int) -> float | None:
        if start_value is None or end_value is None:
            return None
        if years <= 0:
            return None
        if start_value <= 0 or end_value <= 0:
            return None
        return (end_value / start_value) ** (1.0 / years) - 1.0

    @classmethod
    def compute_window_cagr(cls, values_by_year: dict[int, float], window_years: int) -> float | None:
        if not values_by_year:
            return None
        if window_years <= 0:
            return None

        end_year = max(values_by_year)
        start_year = end_year - window_years

        start_value = values_by_year.get(start_year)
        end_value = values_by_year.get(end_year)

        return cls.compute_cagr(start_value=start_value, end_value=end_value, years=window_years)

    @staticmethod
    def representative_growth(
        cagrs: list[float | None],
        cap_floor: float = -0.15,
        cap_ceiling: float = 0.25,
        apply_cap: bool = True,
    ) -> float | None:
        usable = [value for value in cagrs if value is not None]
        if not usable:
            return None
        if apply_cap:
            usable = [max(cap_floor, min(cap_ceiling, value)) for value in usable]
        return float(median(usable))

    @staticmethod
    def growth_dispersion(cagrs: list[float | None]) -> float | None:
        usable = sorted(value for value in cagrs if value is not None)
        if len(usable) < 2:
            return None
        return float(usable[-1] - usable[0])

    @staticmethod
    def classify_history_quality(growth_dispersion: float | None, growth_input_count: int) -> str:
        if growth_input_count < 3:
            return "Limited"
        if growth_dispersion is None:
            return "Moderate"
        if growth_dispersion >= 0.30:
            return "Volatile"
        if growth_dispersion >= 0.15:
            return "Moderate"
        return "Stable"

    @staticmethod
    def expectation_gap(historical_growth_estimate: float | None, implied_growth: float | None) -> float | None:
        if historical_growth_estimate is None or implied_growth is None:
            return None
        return historical_growth_estimate - implied_growth

    @staticmethod
    def classify_assessment(expectation_gap: float | None) -> str:
        if expectation_gap is None:
            return "Unavailable"
        if expectation_gap >= 0.06:
            return "Very Conservative Expectations"
        if expectation_gap >= 0.03:
            return "Conservative Expectations"
        if expectation_gap >= -0.03:
            return "Reasonable Expectations"
        if expectation_gap >= -0.06:
            return "Optimistic Expectations"
        return "Very Optimistic Expectations"
