import pandas as pd

from quantlab.strategies.qvm.historical.repositories import (
    CompaniesMarketCapHistoricalValuationRepository,
)


def test_historical_valuation_repository_applies_formation_year_cutoff() -> None:
    repo = CompaniesMarketCapHistoricalValuationRepository()

    data = repo.load("MSFT", 2019)

    assert data["ticker"] == "MSFT"
    assert data["current_pe"] == 25.9
    assert data["historical_pe_values"] == [11.7, 11.4, 15.9, 33.6, 23.1, 49.9, 21.9, 25.9]
    assert max(data["historical_pe_values"]) <= 49.9
    assert data["historical_average_pe"] > 0
    assert data["historical_median_pe"] > 0
    assert data["formation_year"] == 2019


def test_historical_valuation_repository_rejects_future_pe_rows() -> None:
    repo = CompaniesMarketCapHistoricalValuationRepository()

    df = pd.DataFrame({
        "Year": [2019, 2020],
        "pe_ratio": [20.0, 25.0],
    })

    result = repo._filter_years(df, 2019)

    assert result["Year"].tolist() == [2019]
    assert result["pe_ratio"].tolist() == [20.0]
