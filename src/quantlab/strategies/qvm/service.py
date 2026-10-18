from .analysis.scoring import calculate_score
from .analysis.valuation import compute_modern_regime_stats
from .models import Company
from .providers.companiesmarketcap import CompaniesMarketCapProvider
from .providers.yahoo import YahooProvider
from .market.service import fetch_market_facts
from .market.signals import compute_signals
from .portfolio.action import compute_action

import pandas as pd


def _recompute_percentile(historical_pe_values: list[float], current_pe: float) -> float | None:
    """Rank current_pe against the full historical distribution."""
    if not historical_pe_values:
        return None
    series = pd.Series(historical_pe_values + [current_pe]).dropna().sort_values()
    if series.empty:
        return None

    values = [float(value) for value in series.tolist()]
    rank = sum(1 for value in values if value <= float(current_pe))
    return float((rank - 1) / max(len(values) - 1, 1))


def analyse_company(ticker: str) -> Company:

    metrics_provider = YahooProvider()
    valuation_provider = CompaniesMarketCapProvider()

    company = metrics_provider.load(ticker)

    # Capture live PE from Yahoo before CompaniesMarketCap overwrites valuation_facts
    live_pe = company.valuation_facts.current_pe
    live_pe_source = company.valuation_facts.current_pe_source

    valuation_company = valuation_provider.load(ticker)

    company.valuation_facts = valuation_company.valuation_facts
    company.valuation_facts.requested_historical_years = valuation_company.valuation_facts.requested_historical_years
    company.valuation_facts.valid_pe_count = valuation_company.valuation_facts.valid_pe_count
    company.valuation_facts.outliers_removed = valuation_company.valuation_facts.outliers_removed
    company.valuation_facts.used_pe_count = valuation_company.valuation_facts.used_pe_count

    # Override current_pe with live Yahoo value and recompute percentile
    if live_pe is not None:
        company.valuation_facts.current_pe = live_pe
        company.valuation_facts.current_pe_source = live_pe_source
        hist = company.valuation_facts.historical_pe_values or []
        if hist:
            company.valuation_facts.historical_percentile = _recompute_percentile(hist, live_pe)

    modern_years, modern_obs, modern_median, modern_percentile = compute_modern_regime_stats(
        company.valuation_facts.historical_pe_values,
        company.valuation_facts.current_pe,
    )
    company.valuation_facts.modern_regime_years = modern_years
    company.valuation_facts.modern_used_pe_count = modern_obs
    company.valuation_facts.modern_median_pe = modern_median
    company.valuation_facts.modern_percentile = modern_percentile

    if not company.name and valuation_company.name:
        company.name = valuation_company.name

    # Market / Momentum
    market_facts = fetch_market_facts(ticker)
    company.market_facts = market_facts
    signals = compute_signals(market_facts)
    company.momentum.score = signals.score
    company.momentum.summary = signals.summary
    company.momentum.recommendation = signals.assessment
    company.momentum.reason = signals.reason

    calculate_score(company)

    # Portfolio Action (after scoring so quality/valuation scores are ready)
    company.portfolio = compute_action(
        ticker=ticker,
        quality_score=company.quality.score,
        valuation_band=company.valuation.valuation_band,
        intrinsic_assessment=company.reverse_dcf.assessment,
        assessment=signals.assessment,
        trend=signals.trend or "",
        rs=signals.relative_strength or "",
        pullback=signals.pullback or "",
    )

    return company