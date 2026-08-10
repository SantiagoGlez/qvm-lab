from quantlab.strategies.qvm.portfolio.action import compute_action


def test_portfolio_action_rules_for_unowned_companies(monkeypatch) -> None:
    monkeypatch.setattr("quantlab.strategies.qvm.portfolio.action.owns", lambda ticker: False)

    decision = compute_action(
        ticker="TEST",
        quality_score=90.0,
        valuation_band="Cheap",
        assessment="Attractive",
        trend="Excellent",
        rs="Excellent",
        pullback="Excellent",
    )

    assert decision.action == "Buy"
    assert decision.owned is False
    assert "High-quality business" in decision.company_reason
    assert decision.portfolio_reason.startswith("The company combines")


def test_portfolio_action_rules_for_owned_companies() -> None:
    from quantlab.strategies.qvm.portfolio import action as portfolio_action

    portfolio_action.owns = lambda ticker: True

    decision = compute_action(
        ticker="TEST",
        quality_score=40.0,
        valuation_band=None,
        assessment="Weak",
        trend="Weak",
        rs="Weak",
        pullback="Weak",
    )

    assert decision.action == "Reduce"
    assert decision.owned is True
    assert decision.market_reason == ""
