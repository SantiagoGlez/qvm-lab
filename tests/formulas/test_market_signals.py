from quantlab.strategies.qvm.market.models import MarketFacts
from quantlab.strategies.qvm.market.signals import compute_signals


def test_market_signal_rules_classify_trend_and_pullback() -> None:
    facts = MarketFacts(
        current_price=110.0,
        sma_50=100.0,
        sma_200=90.0,
        rs_6m=0.20,
        rs_12m=0.10,
        distance_from_52w_high_pct=-0.15,
    )

    signals = compute_signals(facts)

    assert signals.trend == "Excellent"
    assert signals.relative_strength == "Strong"
    assert signals.pullback == "Excellent"
    assert signals.assessment == "Attractive"


def test_market_signals_treat_missing_inputs_as_unknown() -> None:
    facts = MarketFacts()

    signals = compute_signals(facts)

    assert signals.trend == "Unknown"
    assert signals.relative_strength == "Unknown"
    assert signals.pullback == "Unknown"
    assert signals.assessment == "Weak"


def test_market_assessment_uses_stabilizing_for_neutral_trend_after_pullback() -> None:
    facts = MarketFacts(
        current_price=99.0,
        sma_50=95.0,
        sma_200=100.0,
        rs_6m=-0.20,
        rs_12m=-0.15,
        distance_from_52w_high_pct=-0.25,
    )

    signals = compute_signals(facts)

    assert signals.trend == "Neutral"
    assert signals.pullback == "Strong"
    assert signals.assessment == "Stabilizing"
