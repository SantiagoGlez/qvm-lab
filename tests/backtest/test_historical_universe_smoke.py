import csv
from pathlib import Path

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


FORMATION_YEAR = 2019


def _load_universe() -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    companies_csv = repo_root / "data" / "qvm" / "companies.csv"
    with companies_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        tickers = [str(row.get("ticker", "")).strip().upper() for row in reader]

    return [ticker for ticker in tickers if ticker]


UNIVERSE = _load_universe()
FORMATION_YEARS = list(range(2015, 2026))


@pytest.mark.parametrize("ticker", UNIVERSE)
def test_historical_universe_single_year_smoke(ticker: str) -> None:
    """Same-year universe smoke test for a small real list of companies.

    The goal is to validate that the repository + adapter + scoring chain works
    consistently across multiple companies under one formation-year cutoff.
    """
    val_repo = CompaniesMarketCapHistoricalValuationRepository()
    fin_repo = CompaniesMarketCapHistoricalFinancialRepository()

    try:
        valuation_data = val_repo.load(ticker, FORMATION_YEAR)
        financial_data = fin_repo.load(ticker, FORMATION_YEAR)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[{ticker}] GAP: {exc}")
        pytest.skip(f"Missing historical slice for {ticker}: {exc}")

    company = HistoricalValuationAdapter().adapt(ticker, valuation_data)
    quality_company = HistoricalQualityAdapter().adapt(ticker, financial_data)

    for field, value in quality_company.metrics.__dict__.items():
        if value is not None:
            setattr(company.metrics, field, value)

    calculate_score(company)

    missing = ", ".join(company.quality.missing_metrics) if company.quality.missing_metrics else "none"
    print(
        f"[{ticker}] valuation={company.valuation.score:.1f} | "
        f"quality={company.quality.score:.1f} | "
        f"overall={overall_score(company):.1f} | "
        f"coverage={company.quality.coverage:.0%} | "
        f"missing={missing}"
    )

    assert company.valuation.score >= 0
    assert company.quality.score >= 0
    assert overall_score(company) >= 0
    assert company.valuation.summary
    assert company.quality.summary


@pytest.mark.parametrize("formation_year", FORMATION_YEARS)
def test_historical_universe_multi_year_smoke(formation_year: int) -> None:
    """Multi-year validation of the historical QVM scoring pipeline.

    This remains intentionally narrow: same universe, same production scoring logic,
    and a strict <= formation_year cutoff. It does not add momentum, ranking, or
    portfolio construction yet.
    """
    val_repo = CompaniesMarketCapHistoricalValuationRepository()
    fin_repo = CompaniesMarketCapHistoricalFinancialRepository()

    processed = 0
    for ticker in UNIVERSE:
        try:
            valuation_data = val_repo.load(ticker, formation_year)
            financial_data = fin_repo.load(ticker, formation_year)
        except (FileNotFoundError, ValueError) as exc:
            print(f"[{formation_year}] {ticker}: GAP={exc}")
            continue

        company = HistoricalValuationAdapter().adapt(ticker, valuation_data)
        quality_company = HistoricalQualityAdapter().adapt(ticker, financial_data)

        for field, value in quality_company.metrics.__dict__.items():
            if value is not None:
                setattr(company.metrics, field, value)

        calculate_score(company)

        missing = ", ".join(company.quality.missing_metrics) if company.quality.missing_metrics else "none"
        print(
            f"[{formation_year}] {ticker}: valuation={company.valuation.score:.1f} | "
            f"quality={company.quality.score:.1f} | "
            f"overall={overall_score(company):.1f} | "
            f"coverage={company.quality.coverage:.0%} | "
            f"missing={missing}"
        )

        assert company.valuation.score >= 0
        assert company.quality.score >= 0
        assert overall_score(company) >= 0
        assert company.valuation.summary
        assert company.quality.summary
        processed += 1

    assert processed > 0, f"No companies could be scored for formation year {formation_year}"
