import pandas as pd
import pytest

from quantlab.strategies.qvm.historical.repositories import (
    HistoricalFinancialRepository,
    HistoricalValuationRepository,
)
from quantlab.strategies.qvm.historical.temporal import (
    HistoricalDataCutoffError,
    filter_to_formation_year,
    validate_history_cutoff,
)


class DummyValuationRepository(HistoricalValuationRepository):
    def load(self, ticker: str, formation_year: int):
        return {"ticker": ticker, "formation_year": formation_year, "historical_pe": [10.0, 11.0]}


class DummyFinancialRepository(HistoricalFinancialRepository):
    def load(self, ticker: str, formation_year: int):
        return {"ticker": ticker, "formation_year": formation_year, "roe": 0.18}


def test_filter_to_formation_year_keeps_data_only_up_to_cutoff() -> None:
    df = pd.DataFrame({"Year": [2017, 2018, 2019, 2020], "pe_ratio": [12.0, 13.0, 14.0, 15.0]})

    filtered = filter_to_formation_year(df, as_of_year=2019)

    assert filtered["Year"].tolist() == [2017, 2018, 2019]


def test_filter_to_formation_year_rejects_future_data() -> None:
    df = pd.DataFrame({"Year": [2018, 2020], "pe_ratio": [12.0, 15.0]})

    with pytest.raises(HistoricalDataCutoffError):
        validate_history_cutoff(df, as_of_year=2019)


def test_repository_contract_requires_ticker_and_year_inputs() -> None:
    valuation_repo = DummyValuationRepository()
    financial_repo = DummyFinancialRepository()

    assert valuation_repo.load("MSFT", 2019)["formation_year"] == 2019
    assert financial_repo.load("MSFT", 2019)["ticker"] == "MSFT"
