from quantlab.strategies.qvm.models import Company, AnalysisResult
from quantlab.strategies.qvm.portfolio.models import PortfolioDecision

from quantlab.strategies.qvm.options.screen import screen_call_candidates


def _make_company(
    ticker: str,
    *,
    quality_score: float,
    valuation_band: str,
    intrinsic_assessment: str,
    market_assessment: str,
    action: str,
) -> Company:
    company = Company(
        ticker=ticker,
        name=ticker,
        quality=AnalysisResult(score=quality_score),
        valuation=AnalysisResult(valuation_band=valuation_band),
        momentum=AnalysisResult(recommendation=market_assessment),
        portfolio=PortfolioDecision(action=action, owned=False),
    )
    company.reverse_dcf.assessment = intrinsic_assessment
    return company


def test_screen_call_candidates_prioritizes_quality_and_intrinsic_value():
    good = _make_company(
        "NVDA",
        quality_score=92.0,
        valuation_band="Fair Value",
        intrinsic_assessment="Reasonable Expectations",
        market_assessment="Improving",
        action="Add",
    )
    bad = _make_company(
        "EL",
        quality_score=28.0,
        valuation_band="Very Expensive",
        intrinsic_assessment="Very Optimistic Expectations",
        market_assessment="Weak",
        action="Reject",
    )

    results = screen_call_candidates([good, bad])
    tickers = {row["ticker"] for row in results}

    assert "NVDA" in tickers
    assert "EL" not in tickers
    assert all(row["maturity_months"] in {6, 9, 12} for row in results)
    assert min(row["score"] for row in results) >= 0.0
