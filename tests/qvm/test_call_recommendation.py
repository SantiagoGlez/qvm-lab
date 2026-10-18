from quantlab.strategies.qvm.models import Company, AnalysisResult
from quantlab.strategies.qvm.portfolio.models import PortfolioDecision
from quantlab.strategies.qvm.options.recommendation import (
    build_call_payoff_table,
    build_call_recommendation,
    build_standalone_call_report,
    estimate_best_call_contract,
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
    assert recommendation["suggested_strike"] >= 120.0
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


def test_build_call_recommendation_allows_override_for_weak_liquidity():
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
        ignore_liquidity=True,
    )

    assert recommendation["ignore_liquidity"] is True
    assert recommendation["risk_level_reason"]
    assert "ignoring" in recommendation["trade_status"].lower()


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


def test_build_call_recommendation_uses_watch_when_estimate_is_heuristic(monkeypatch):
    company = _make_company(
        "NVDA",
        quality_score=92.0,
        valuation_band="Cheap",
        intrinsic_assessment="Very Conservative Expectations",
        market_assessment="Improving",
        action="Add",
        current_price=120.0,
    )

    monkeypatch.setattr(
        "quantlab.strategies.qvm.options.recommendation.estimate_best_call_contract",
        lambda ticker, current_price, maturity_months, target_delta=None: {
            "source": "heuristic",
            "strike": 132.0,
            "premium_estimate": 2.5,
            "break_even": 134.5,
            "fallback_reason": "fallback because live option chain is unavailable or incomplete: TypeError",
        },
    )

    recommendation = build_call_recommendation(
        company,
        maturity_months=9,
        option_market_data={"NVDA": {"iv": 0.62, "volume": 900000, "open_interest": 25000}},
    )

    assert recommendation["estimated_option_source"] == "heuristic"
    assert recommendation["estimated_option_fallback_reason"]
    assert recommendation["decision"] == "watch"
    assert "heuristic" in recommendation["decision_reason"].lower()


def test_estimate_best_call_contract_handles_string_expiries(monkeypatch):
    pd = __import__("pandas")

    class FakeHistory:
        empty = False
        index = [pd.Timestamp("2026-10-18", tz="America/New_York")]

    class FakeRow:
        strike = 102.0
        delta = 0.5
        bid = 1.95
        ask = 2.05
        lastPrice = 2.0
        volume = 2500
        openInterest = 5000

    class FakeCalls:
        empty = False

        def __iter__(self):
            return iter([FakeRow()])

        def itertuples(self, index=False):
            return [FakeRow()]

    class FakeChain:
        calls = FakeCalls()

    class FakeTicker:
        options = ["2026-11-20"]

        def history(self, period):
            return FakeHistory()

        def option_chain(self, expiry):
            return FakeChain()

    monkeypatch.setattr("quantlab.strategies.qvm.options.recommendation.yf.Ticker", lambda ticker: FakeTicker())

    estimate = __import__("quantlab.strategies.qvm.options.recommendation", fromlist=["estimate_best_call_contract"]).estimate_best_call_contract(
        "TEST",
        100.0,
        9,
    )

    assert estimate["source"] == "live_chain"
    assert estimate["strike"] == 102.0
    assert estimate["premium_estimate"] == 2.0
    assert estimate["break_even"] == 104.0


def test_estimate_best_call_contract_uses_selected_option_row_values(monkeypatch):
    pd = __import__("pandas")

    class FakeHistory:
        empty = False
        index = [pd.Timestamp("2026-10-18", tz="America/New_York")]

    class FakeRow:
        strike = 102.0
        delta = 0.5
        bid = 1.95
        ask = 2.05
        lastPrice = 2.0
        volume = 2500
        openInterest = 5000

    class FakeCalls:
        empty = False

        def __iter__(self):
            return iter([FakeRow()])

        def itertuples(self, index=False):
            return [FakeRow()]

    class FakeChain:
        calls = FakeCalls()

    class FakeTicker:
        options = [pd.Timestamp("2026-11-20")]

        def history(self, period):
            return FakeHistory()

        def option_chain(self, expiry):
            return FakeChain()

    monkeypatch.setattr("quantlab.strategies.qvm.options.recommendation.yf.Ticker", lambda ticker: FakeTicker())

    estimate = __import__("quantlab.strategies.qvm.options.recommendation", fromlist=["estimate_best_call_contract"]).estimate_best_call_contract(
        "TEST",
        100.0,
        9,
    )

    assert estimate["source"] == "live_chain"
    assert estimate["strike"] == 102.0
    assert estimate["premium_estimate"] == 2.0
    assert estimate["break_even"] == 104.0


def test_build_call_payoff_table_shows_break_even_and_profit_levels():
    rows = build_call_payoff_table(340.59, 350.0, 39.29, target=415.52, break_even=389.29)

    assert any(row["stock_price"] == 389.29 for row in rows)
    assert any(row["profit_contract"] == 0.0 for row in rows)
    assert any(row["profit_contract"] > 0.0 for row in rows)
    assert any(row["profit_contract"] < 0.0 for row in rows)
    assert "profit_contract_pct" in rows[0]
    assert "stock_direct_profit" in rows[0]
    assert rows[0]["stock_direct_profit"] < 0.0
    assert any(389.29 < row["stock_price"] < 415.52 for row in rows)


def test_build_standalone_call_report_returns_option_only_summary(monkeypatch):
    pd = __import__("pandas")

    class FakeHistory:
        empty = False
        index = [pd.Timestamp("2026-10-18", tz="America/New_York")]

    class FakeRow:
        strike = 350.0
        delta = 0.5
        bid = 38.05
        ask = 39.75
        lastPrice = 39.29
        volume = 1439
        openInterest = 4747

    class FakeCalls:
        empty = False

        def __iter__(self):
            return iter([FakeRow()])

        def itertuples(self, index=False):
            return [FakeRow()]

    class FakeChain:
        calls = FakeCalls()

    class FakeTicker:
        options = ["2027-06-17"]

        def history(self, period):
            return FakeHistory()

        def option_chain(self, expiry):
            return FakeChain()

    monkeypatch.setattr("quantlab.strategies.qvm.options.recommendation.yf.Ticker", lambda ticker: FakeTicker())

    report = build_standalone_call_report("GOOGL", current_price=340.59, maturity_months=9)

    assert report["ticker"] == "GOOGL"
    assert report["estimated_option_source"] == "live_chain"
    assert report["suggested_strike"] == 350.0
    assert report["break_even"] > report["current_price"]
    assert "payoff_table" in report
    assert report["payoff_table"][0]["pct_move"] < 0


def test_estimate_best_call_contract_keeps_live_chain_for_weak_liquidity(monkeypatch):
    pd = __import__("pandas")

    class FakeHistory:
        empty = False
        index = [pd.Timestamp("2026-10-18", tz="America/New_York")]

    class FakeRow:
        strike = 40.0
        delta = 0.5
        bid = 3.2
        ask = 3.9
        lastPrice = 3.5
        volume = 1.0
        openInterest = 15.0

    class FakeCalls:
        empty = False

        def __iter__(self):
            return iter([FakeRow()])

        def itertuples(self, index=False):
            return [FakeRow()]

    class FakeChain:
        calls = FakeCalls()

    class FakeTicker:
        options = ["2027-06-17"]

        def history(self, period):
            return FakeHistory()

        def option_chain(self, expiry):
            return FakeChain()

    monkeypatch.setattr("quantlab.strategies.qvm.options.recommendation.yf.Ticker", lambda ticker: FakeTicker())

    estimate = estimate_best_call_contract("AR", 38.65, 9)

    assert estimate["source"] == "live_chain"
    assert estimate["weak_liquidity"] is True
    assert estimate["fallback_reason"]


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
