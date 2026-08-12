import pytest

from quantlab.strategies.qvm.analysis.quality import analyse_quality
from quantlab.strategies.qvm.analysis.valuation import analyse_valuation
from quantlab.strategies.qvm.historical.adapters import (
    HistoricalQualityAdapter,
    HistoricalValuationAdapter,
)


def test_historical_valuation_adapter_maps_repo_data_to_company_model() -> None:
    repo_data = {
        "ticker": "MSFT",
        "formation_year": 2019,
        "historical_pe_values": [11.7, 11.4, 15.9, 33.6, 23.1, 49.9, 21.9, 25.9],
        "historical_average_pe": 24.1,
        "historical_median_pe": 21.9,
        "historical_percentile": 0.5,
        "current_pe": 25.9,
        "used_pe_count": 8,
    }

    company = HistoricalValuationAdapter().adapt("MSFT", repo_data)

    assert company.ticker == "MSFT"
    assert company.valuation_facts.current_pe == 25.9
    assert company.valuation_facts.historical_pe_values[-1] == 25.9
    assert company.valuation_facts.historical_average_pe == 24.1
    assert analyse_valuation(company).score > 0


def test_historical_quality_adapter_maps_y_minus_1_financials_to_company_metrics() -> None:
    repo_data = {
        "ticker": "MSFT",
        "formation_year": 2019,
        "year": 2018,
        "revenue": 118_450_000_000.0,
        "net_income": 39_920_000_000.0,
        "eps": 4.35,
        "operating_margin": 0.3553,
        "operating_cash_flow": 52_185_000_000.0,
        "capex": 13_925_000_000.0,
        "net_assets": 82_710_000_000.0,
        "total_debt": 81_800_000_000.0,
        "cash": 133_660_000_000.0,
        "shares_outstanding": 7_690_000_000.0,
    }

    company = HistoricalQualityAdapter().adapt("MSFT", repo_data)

    assert company.metrics.roe == pytest.approx(0.4827, abs=1e-4)
    assert company.metrics.operating_margin == pytest.approx(0.3553)
    assert company.metrics.net_debt_ebitda is not None
    assert company.metrics.debt_to_ebitda is not None
    assert company.metrics.fcf_margin == pytest.approx((52_185_000_000.0 - 13_925_000_000.0) / 118_450_000_000.0)
    assert company.metrics.fcf_conversion == pytest.approx((52_185_000_000.0 - 13_925_000_000.0) / 39_920_000_000.0)
    assert analyse_quality(company).score > 0
