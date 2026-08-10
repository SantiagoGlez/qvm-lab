from quantlab.strategies.qvm.analysis.quality import analyse_quality
from quantlab.strategies.qvm.analysis.valuation import analyse_valuation
from quantlab.strategies.qvm.market.models import MarketFacts
from quantlab.strategies.qvm.market.signals import compute_signals
from quantlab.strategies.qvm.models import Company, CompanyMetrics


def test_end_to_end_rules_still_produce_consistent_recommendations() -> None:
    company = Company(
        ticker="MSFT",
        metrics=CompanyMetrics(forward_pe=28.0, trailing_pe=30.0),
    )
    company.valuation_facts.historical_average_pe = 25.0
    company.valuation_facts.historical_percentile = 0.30
    company.valuation_facts.current_pe = 28.0

    valuation = analyse_valuation(company)
    quality = analyse_quality(company)

    market = MarketFacts(
        current_price=100.0,
        sma_50=90.0,
        sma_200=80.0,
        rs_6m=0.12,
        rs_12m=0.08,
        distance_from_52w_high_pct=-0.08,
    )
    signals = compute_signals(market)

    assert valuation.recommendation == "WATCH"
    assert quality.recommendation == "Weak"
    assert signals.assessment == "Improving"
