import pytest

from quantlab.strategies.qvm.analysis.overall import overall_score
from quantlab.strategies.qvm.analysis.scoring import calculate_score
from quantlab.strategies.qvm.historical.adapters import (
    HistoricalQualityAdapter,
    HistoricalValuationAdapter,
)
from quantlab.strategies.qvm.historical.repositories import (
    CompaniesMarketCapHistoricalFinancialRepository,
    CompaniesMarketCapHistoricalValuationRepository,
)


# Historical smoke test: this is a formation-year snapshot for a real company.
# The score is intentionally time-specific and tied to the Y-1 financial rule
# and the valuation data available by the formation year, not to a magic constant.
def test_historical_single_year_qvm_smoke_test() -> None:
    val_repo = CompaniesMarketCapHistoricalValuationRepository()
    fin_repo = CompaniesMarketCapHistoricalFinancialRepository()

    valuation_data = val_repo.load("MSFT", 2019)
    financial_data = fin_repo.load("MSFT", 2019)

    company = HistoricalValuationAdapter().adapt("MSFT", valuation_data)
    quality_company = HistoricalQualityAdapter().adapt("MSFT", financial_data)

    for field, value in quality_company.metrics.__dict__.items():
        if value is not None:
            setattr(company.metrics, field, value)

    calculate_score(company)

    assert company.metrics.roe == pytest.approx(0.4826502237, abs=1e-4)
    assert company.metrics.operating_margin == pytest.approx(0.3553)
    assert company.valuation.score == pytest.approx(52.4)
    assert company.quality.score == pytest.approx(96.7)
    assert overall_score(company) == pytest.approx(74.5)
    assert company.valuation.summary.startswith("Historical PE Percentile: 71%")
    assert "ROE=48.3%" in company.quality.summary
