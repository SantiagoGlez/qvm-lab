from .analysis.scoring import calculate_score
from .models import Company
from .providers.companiesmarketcap import CompaniesMarketCapProvider
from .providers.yahoo import YahooProvider
from .market.service import fetch_market_facts
from .market.signals import compute_signals
from .portfolio.action import compute_action

import pandas as pd


def _recompute_percentile(historical_pe_values: list[float], current_pe: float) -> float | None:
    """Rank current_pe within the historical distribution (current_pe replaces last element)."""
    if not historical_pe_values:
        return None
    series = pd.Series(historical_pe_values[:-1] + [current_pe])
    return float(series.rank(method="average", pct=True).iloc[-1])


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
        assessment=signals.assessment,
        trend=signals.trend or "",
        rs=signals.relative_strength or "",
        pullback=signals.pullback or "",
    )

    return company