from quantlab.strategies.qvm.models import Company, AnalysisResult
from quantlab.strategies.qvm.portfolio.models import PortfolioDecision
from quantlab.strategies.qvm.options.recommendation import (
    build_call_recommendation,
    validate_recommendation_with_google_finance,
)


def _make_company(
    ticker: str,
    *,
    quality_score: float,
    valuation_band: str,
    intrinsic_assessment: str,
    market_assessment: str,
    action: str,
    current_price: float,
) -> Company:
    company = Company(
        ticker=ticker,
        name=ticker,
        quality=AnalysisResult(score=quality_score),
        valuation=AnalysisResult(valuation_band=valuation_band),
        momentum=AnalysisResult(recommendation=market_assessment),
        portfolio=PortfolioDecision(action=action, owned=False),
    )
    company.market_facts.current_price = current_price
    company.reverse_dcf.assessment = intrinsic_assessment
    return company


def test_build_call_recommendation_creates_trade_level_output():
    company = _make_company(
        "NVDA",
        quality_score=92.0,
        valuation_band="Cheap",
        intrinsic_assessment="Very Conservative Expectations",
        market_assessment="Improving",
        action="Add",
        current_price=120.0,
    )

    recommendation = build_call_recommendation(
        company,
        maturity_months=9,
        option_market_data={
            "NVDA": {"iv": 0.62, "volume": 900000, "open_interest": 25000},
        },
    )

    assert recommendation["ticker"] == "NVDA"
    assert recommendation["maturity_months"] == 9
    assert recommendation["current_price"] == 120.0
    assert recommendation["suggested_strike"] > 120.0
    assert recommendation["max_loss"] > 0
    assert recommendation["break_even"] > recommendation["suggested_strike"]
    assert recommendation["confidence"] in {"high", "medium", "low"}
    assert recommendation["liquidity_ok"] is True
    assert recommendation["risk_level"] in {"controlled", "cautious", "aggressive"}


def test_build_call_recommendation_rejects_weak_option_chain():
    company = _make_company(
        "XYZ",
        quality_score=84.0,
        valuation_band="Fair Value",
        intrinsic_assessment="Conservative Expectations",
        market_assessment="Improving",
        action="Add",
        current_price=50.0,
    )

    recommendation = build_call_recommendation(
        company,
        maturity_months=9,
        option_market_data={
            "XYZ": {"iv": 0.95, "volume": 12000, "open_interest": 350},
        },
    )

    assert recommendation["liquidity_ok"] is False
    assert recommendation["risk_level"] == "aggressive"
    assert "liquidity" in recommendation["trade_status"].lower()


def test_build_call_recommendation_returns_final_execution_decision():
    company = _make_company(
        "NVDA",
        quality_score=92.0,
        valuation_band="Cheap",
        intrinsic_assessment="Very Conservative Expectations",
        market_assessment="Improving",
        action="Add",
        current_price=120.0,
    )

    recommendation = build_call_recommendation(
        company,
        maturity_months=9,
        option_market_data={"NVDA": {"iv": 0.62, "volume": 900000, "open_interest": 25000}},
    )

    assert recommendation["decision"] in {"approve", "watch", "reject"}
    assert recommendation["decision_reason"]


def test_validate_recommendation_with_google_finance_uses_external_audit(monkeypatch):
    company = _make_company(
        "NVDA",
        quality_score=92.0,
        valuation_band="Cheap",
        intrinsic_assessment="Very Conservative Expectations",
        market_assessment="Improving",
        action="Add",
        current_price=120.0,
    )
    recommendation = build_call_recommendation(company, maturity_months=9)

    captured = {}

    def fake_audit(report_text: str, **kwargs):
        captured["report_text"] = report_text
        return type(
            "AuditResult",
            (),
            {"success": True, "response": "Verdict: Pass\nConfidence Score (0-100): 82", "error": ""},
        )()

    monkeypatch.setattr(
        "quantlab.strategies.qvm.options.recommendation.run_google_finance_audit",
        fake_audit,
    )

    result = validate_recommendation_with_google_finance(company, recommendation)

    assert result["google_finance_success"] is True
    assert result["google_finance_verdict"] == "Pass"
    assert "NVDA" in captured["report_text"]
