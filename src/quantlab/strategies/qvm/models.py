from datetime import datetime, timezone
from pydantic import BaseModel, Field

from .market.models import MarketFacts
from .portfolio.models import PortfolioDecision


class CompanyMetrics(BaseModel):
    forward_pe: float | None = None
    trailing_pe: float | None = None

    market_cap: float | None = None

    roe: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    revenue_cagr: float | None = None
    eps_cagr: float | None = None
    revenue_cagr_years: int | None = None
    eps_cagr_years: int | None = None
    fcf_margin: float | None = None
    fcf_conversion: float | None = None
    net_cash: float | None = None
    net_debt_ebitda: float | None = None
    interest_coverage: float | None = None
    debt_to_ebitda: float | None = None


class AnalysisResult(BaseModel):
    score: float = 0.0

    summary: str = ""

    recommendation: str = ""

    reason: str = ""

    coverage: float = 0.0

    missing_metrics: list[str] = Field(default_factory=list)

    eligible: bool = False

    valuation_band: str | None = None

class ValuationFacts(BaseModel):
    """Raw valuation metrics used by the valuation analysis."""

    forward_pe: float | None = None
    trailing_pe: float | None = None

    historical_pe_values: list[float] | None = None
    historical_average_pe: float | None = None
    historical_median_pe: float | None = None
    historical_percentile: float | None = None
    current_pe: float | None = None
    current_pe_source: str | None = None

    requested_historical_years: int | None = None
    valid_pe_count: int | None = None
    outliers_removed: int | None = None
    used_pe_count: int | None = None

    discount_to_average_pct: float | None = None
    discount_to_median_pct: float | None = None


class ReverseDCFAnalysis(BaseModel):
    implied_growth: float | None = None

    discount_rate: float = 0.09
    terminal_growth: float = 0.03
    projection_years: int = 10

    revenue_cagr_5y: float | None = None
    revenue_cagr_10y: float | None = None

    eps_cagr_5y: float | None = None
    eps_cagr_10y: float | None = None

    fcf_cagr_5y: float | None = None
    fcf_cagr_10y: float | None = None

    historical_growth_estimate: float | None = None
    historical_growth_estimate_raw: float | None = None
    representative_growth_uses_cap: bool = True
    representative_growth_cap_floor: float = -0.15
    representative_growth_cap_ceiling: float = 0.25
    growth_input_count: int = 0
    growth_dispersion: float | None = None
    history_quality: str = "Unknown"

    revenue_growth_source: str = "Unavailable"
    eps_growth_source: str = "Unavailable"
    fcf_growth_source: str = "Unavailable"

    expectation_gap: float | None = None

    assessment: str = "Unavailable"

class Company(BaseModel):

    ticker: str

    name: str | None = None

    sector: str | None = None

    industry: str | None = None

    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    metrics: CompanyMetrics = Field(default_factory=CompanyMetrics)

    valuation: AnalysisResult = Field(default_factory=AnalysisResult)

    quality: AnalysisResult = Field(default_factory=AnalysisResult)

    momentum: AnalysisResult = Field(default_factory=AnalysisResult)

    growth: AnalysisResult = Field(default_factory=AnalysisResult)

    valuation_facts: ValuationFacts = Field(default_factory=ValuationFacts)

    reverse_dcf: ReverseDCFAnalysis = Field(default_factory=ReverseDCFAnalysis)

    market_facts: MarketFacts = Field(default_factory=MarketFacts)

    portfolio: PortfolioDecision = Field(default_factory=PortfolioDecision)

    valuation: AnalysisResult = Field(default_factory=AnalysisResult)



