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
