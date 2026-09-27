import pandas as pd

import quantlab.strategies.qvm.providers.yahoo as yahoo_module
from quantlab.strategies.qvm.providers.yahoo import YahooProvider


class _FakeTicker:
    def __init__(self) -> None:
        self.ticker = "FAKE"
        self.info = {
            "shortName": "Fake Co",
            "sector": "Tech",
            "industry": "Software",
            "marketCap": 1000.0,
            "sharesOutstanding": 10.0,
            "forwardPE": 20.0,
            "trailingPE": 25.0,
        }
        self.income_stmt = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): {
                    "Total Revenue": 100.0,
                },
                pd.Timestamp("2023-12-31"): {
                    "Total Revenue": 90.0,
                },
            }
        )
        self.cash_flow = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): {
                    "Operating Cash Flow": 45.0,
                    "Capital Expenditure": -18.0,
                },
                pd.Timestamp("2023-12-31"): {
                    "Operating Cash Flow": 30.0,
                    "Capital Expenditure": -10.0,
                },
            }
        )
        self.quarterly_cashflow = pd.DataFrame()


class _FinancialHealthTicker:
    def __init__(self, *, net_debt: float | None, total_debt: float | None, cash_total: float | None) -> None:
        self.ticker = "FAKE"
        self.income_stmt = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): {
                    "EBITDA": 100.0,
                    "EBIT": 80.0,
                    "Interest Expense": -10.0,
                }
            }
        )
        bal_row: dict[str, float] = {}
        if net_debt is not None:
            bal_row["Net Debt"] = float(net_debt)
        if total_debt is not None:
            bal_row["Total Debt"] = float(total_debt)
        if cash_total is not None:
            bal_row["Cash Cash Equivalents And Short Term Investments"] = float(cash_total)
        self.balance_sheet = pd.DataFrame({pd.Timestamp("2024-12-31"): bal_row})


def test_build_capex_resilience_inputs_uses_latest_annual_values() -> None:
    provider = YahooProvider()
    stock = _FakeTicker()

    inputs = provider._build_capex_resilience_inputs(stock=stock, net_cash=25.0)

    assert inputs.revenue == 100.0
    assert inputs.operating_cash_flow == 45.0
    assert inputs.capex == -18.0
    assert inputs.free_cash_flow == 27.0
    assert inputs.revenue_by_year == {2023: 90.0, 2024: 100.0}
    assert inputs.operating_cash_flow_by_year == {2023: 30.0, 2024: 45.0}
    assert inputs.capex_by_year == {2023: -10.0, 2024: -18.0}
    assert inputs.free_cash_flow_by_year == {2023: 20.0, 2024: 27.0}


def test_load_populates_capex_resilience_from_yahoo_history(monkeypatch) -> None:
    fake_stock = _FakeTicker()
    provider = YahooProvider()

    monkeypatch.setattr(yahoo_module.yf, "Ticker", lambda _: fake_stock)
    monkeypatch.setattr(provider, "_calculate_roic", lambda stock: None)
    monkeypatch.setattr(provider, "_calculate_cagr", lambda stock, label, fallback=None: (None, None))
    monkeypatch.setattr(provider, "_calculate_fcf_metrics", lambda stock: (None, None))
    monkeypatch.setattr(provider, "_calculate_financial_health", lambda stock: (25.0, None, None, None))
    monkeypatch.setattr(provider, "_calculate_live_pe", lambda info: None)
    monkeypatch.setattr(provider, "_historical_pe", lambda stock, ticker: [])
    monkeypatch.setattr(provider, "_current_share_price", lambda info: 100.0)
    monkeypatch.setattr(provider, "_calculate_ttm_fcf", lambda stock: 27.0)
    monkeypatch.setattr(
        provider,
        "_marketcap_historical_series",
        lambda ticker: (
            {2023: 90.0, 2024: 100.0},
            {},
            {2023: 20.0, 2024: 27.0},
            {"revenue": "CompaniesMarketCap Financials", "eps": "Unavailable", "fcf": "CompaniesMarketCap Financials"},
        ),
    )

    company = provider.load("FAKE")

    assert company.capex_resilience.current_revenue == 100.0
    assert company.capex_resilience.current_operating_cash_flow == 45.0
    assert company.capex_resilience.current_capex == -18.0
    assert company.capex_resilience.current_free_cash_flow == 27.0
    assert company.capex_resilience.relevance == "High"
    assert company.capex_resilience.resilience == "Unavailable"


def test_financial_health_prefers_component_net_cash_over_net_debt_field() -> None:
    provider = YahooProvider()
    # Deliberately inconsistent snapshot: Net Debt field says debt-heavy,
    # but components imply net cash.
    stock = _FinancialHealthTicker(net_debt=150.0, total_debt=100.0, cash_total=300.0)

    net_cash, net_debt_ebitda, interest_cov, debt_to_ebitda = provider._calculate_financial_health(stock)

    assert net_cash == 200.0
    assert net_debt_ebitda == -2.0
    assert interest_cov == 8.0
    assert debt_to_ebitda == 1.0


def test_financial_health_falls_back_to_net_debt_when_components_missing() -> None:
    provider = YahooProvider()
    stock = _FinancialHealthTicker(net_debt=120.0, total_debt=None, cash_total=None)

    net_cash, net_debt_ebitda, interest_cov, debt_to_ebitda = provider._calculate_financial_health(stock)

    assert net_cash == -120.0
    assert net_debt_ebitda is None
    assert interest_cov == 8.0
    assert debt_to_ebitda is None