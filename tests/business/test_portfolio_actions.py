from quantlab.strategies.qvm.portfolio.action import compute_action


def test_portfolio_action_rules_for_unowned_companies(monkeypatch) -> None:
    monkeypatch.setattr("quantlab.strategies.qvm.portfolio.action.owns", lambda ticker: False)

    decision = compute_action(
        ticker="TEST",
        quality_score=90.0,
        valuation_band="Cheap",
        intrinsic_assessment="Reasonable Expectations",
        assessment="Attractive",
        trend="Excellent",
        rs="Excellent",
        pullback="Excellent",
    )

    assert decision.action == "Add"
    assert decision.owned is False
    assert "High-quality business" in decision.company_reason
    assert decision.portfolio_reason.startswith("The company ranks")


def test_unowned_excellent_with_mixed_confirmation_is_candidate_to_add(monkeypatch) -> None:
    monkeypatch.setattr("quantlab.strategies.qvm.portfolio.action.owns", lambda ticker: False)

    decision = compute_action(
        ticker="TEST",
        quality_score=85.0,
        valuation_band="Very Expensive",
        intrinsic_assessment="Reasonable Expectations",
        assessment="Improving",
        trend="Strong",
        rs="Neutral",
        pullback="Neutral",
    )

    assert decision.action == "Candidate to Add"
    assert "reserve list" in decision.portfolio_reason


def test_unowned_average_quality_maps_to_watch_when_supportive(monkeypatch) -> None:
    monkeypatch.setattr("quantlab.strategies.qvm.portfolio.action.owns", lambda ticker: False)

    decision = compute_action(
        ticker="TEST",
        quality_score=65.0,
        valuation_band="Fair Value",
        intrinsic_assessment="Reasonable Expectations",
        assessment="Improving",
        trend="Strong",
        rs="Neutral",
        pullback="Neutral",
    )

    assert decision.action == "Watch"


def test_portfolio_action_rules_for_owned_companies() -> None:
    from quantlab.strategies.qvm.portfolio import action as portfolio_action

    portfolio_action.owns = lambda ticker: True

    decision = compute_action(
        ticker="TEST",
        quality_score=40.0,
        valuation_band=None,
        intrinsic_assessment=None,
        assessment="Weak",
        trend="Weak",
        rs="Weak",
        pullback="Weak",
    )

    assert decision.action == "Review"
    assert decision.owned is True
    assert "trend" in decision.market_reason.lower() or "stock" in decision.market_reason.lower()


def test_owned_excellent_with_single_warning_is_keep_monitor() -> None:
    from quantlab.strategies.qvm.portfolio import action as portfolio_action

    portfolio_action.owns = lambda ticker: True

    decision = compute_action(
        ticker="TEST",
        quality_score=90.0,
        valuation_band="Expensive",
        intrinsic_assessment="Reasonable Expectations",
        assessment="Near-highs",
        trend="Strong",
        rs="Strong",
        pullback="Neutral",
    )

    assert decision.action == "Keep (Monitor)"
    assert "mild warning" in decision.portfolio_reason
    assert "Historical valuation" in decision.portfolio_reason
    assert "Intrinsic valuation" in decision.portfolio_reason
