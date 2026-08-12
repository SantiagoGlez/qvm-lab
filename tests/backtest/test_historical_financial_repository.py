from pathlib import Path

import pytest

from quantlab.strategies.qvm.historical.repositories import (
    CompaniesMarketCapHistoricalFinancialRepository,
)


def test_historical_financial_repository_uses_y_minus_1_data() -> None:
    repo = CompaniesMarketCapHistoricalFinancialRepository()

    data = repo.load("MSFT", 2019)

    assert data["ticker"] == "MSFT"
    assert data["formation_year"] == 2019
    assert data["year"] == 2018
    assert data["revenue"] == 118450000000.0
    assert data["net_income"] == 39920000000.0
    assert data["operating_margin"] == 0.3553
    assert data["eps"] == 4.35


def test_historical_financial_repository_computes_cagr_from_reference_year_window() -> None:
    repo = CompaniesMarketCapHistoricalFinancialRepository()

    data = repo.load("MSFT", 2019)

    assert data["revenue_cagr"] == __import__("pytest").approx(0.1543594948, rel=1e-6)
    assert data["eps_cagr"] == __import__("pytest").approx(0.3407164731, rel=1e-6)
    assert data["revenue_cagr_years"] == 3
    assert data["eps_cagr_years"] == 3


def test_historical_financial_repository_rejects_future_rows() -> None:
    repo = CompaniesMarketCapHistoricalFinancialRepository()

    row = repo._select_yearly_snapshot(
        __import__("pandas").DataFrame({"Year": [2018, 2020], "revenue": [1.0, 2.0]}),
        2019,
    )

    assert row["Year"].tolist() == [2018]
    assert row["revenue"].tolist() == [1.0]


def test_historical_financial_repository_enriches_with_sec_probe_fields() -> None:
    probe_path = Path("data/qvm/companiesmarketcap/msft_sec_companyfacts_probe.csv")
    if not probe_path.exists():
        pytest.skip("MSFT SEC probe dataset not available in this workspace")

    repo = CompaniesMarketCapHistoricalFinancialRepository()

    data = repo.load("MSFT", 2019)

    assert data["roic"] is not None
    assert data["operating_cash_flow"] is not None
    assert data["capex"] is not None
    assert data["free_cash_flow"] is not None


def test_historical_financial_repository_prefers_primary_values_over_sec_fallback() -> None:
    repo = CompaniesMarketCapHistoricalFinancialRepository()

    assert repo._prefer_primary_then_fallback(10.0, 20.0) == 10.0
    assert repo._prefer_primary_then_fallback(0.0, 20.0) == 0.0


def test_historical_financial_repository_uses_sec_fallback_when_primary_missing() -> None:
    repo = CompaniesMarketCapHistoricalFinancialRepository()

    assert repo._prefer_primary_then_fallback(None, 20.0) == 20.0
    assert repo._prefer_primary_then_fallback(float("nan"), 20.0) == 20.0
