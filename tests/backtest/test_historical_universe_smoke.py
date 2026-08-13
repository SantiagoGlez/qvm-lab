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
REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "data" / "qvm" / "backtest"
DETAIL_REPORT = REPORT_DIR / "historical_coverage_by_year_company.csv"
YEARLY_REPORT = REPORT_DIR / "historical_coverage_by_year_summary.csv"
COMPANY_REPORT = REPORT_DIR / "historical_coverage_by_company_summary.csv"

_COVERAGE_ROWS: list[dict[str, str]] = []


def _load_universe() -> list[str]:
    companies_csv = REPO_ROOT / "data" / "qvm" / "companies.csv"
    with companies_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        tickers = [str(row.get("ticker", "")).strip().upper() for row in reader]

    return [ticker for ticker in tickers if ticker]


UNIVERSE = _load_universe()
FORMATION_YEARS = list(range(2015, 2026))


def _record_coverage(
    *,
    scope: str,
    formation_year: int,
    ticker: str,
    status: str,
    coverage: float | None,
    valuation_score: float | None,
    quality_score: float | None,
    overall: float | None,
    missing: str,
    note: str,
) -> None:
    _COVERAGE_ROWS.append(
        {
            "scope": scope,
            "formation_year": str(formation_year),
            "ticker": ticker,
            "status": status,
            "coverage": "" if coverage is None else f"{coverage:.4f}",
            "valuation_score": "" if valuation_score is None else f"{valuation_score:.4f}",
            "quality_score": "" if quality_score is None else f"{quality_score:.4f}",
            "overall_score": "" if overall is None else f"{overall:.4f}",
            "missing": missing,
            "note": note,
        }
    )
    _write_coverage_reports()


def _write_coverage_reports() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    sorted_rows = sorted(
        _COVERAGE_ROWS,
        key=lambda row: (
            int(row["formation_year"]),
            row["ticker"],
            row["scope"],
            row["status"],
        ),
    )

    with DETAIL_REPORT.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "scope",
            "formation_year",
            "ticker",
            "status",
            "coverage",
            "valuation_score",
            "quality_score",
            "overall_score",
            "missing",
            "note",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    summary_rows = [row for row in sorted_rows if row["scope"] == "multi_year"]
    if not summary_rows:
        summary_rows = sorted_rows

    year_buckets: dict[int, list[float]] = {}
    company_buckets: dict[str, list[float]] = {}
    for row in summary_rows:
        if row["status"] != "OK" or not row["coverage"]:
            continue

        year = int(row["formation_year"])
        ticker = row["ticker"]
        coverage = float(row["coverage"])
        year_buckets.setdefault(year, []).append(coverage)
        company_buckets.setdefault(ticker, []).append(coverage)

    with YEARLY_REPORT.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["formation_year", "count", "coverage_mean", "coverage_min", "coverage_max"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for year in sorted(year_buckets):
            coverages = year_buckets[year]
            writer.writerow(
                {
                    "formation_year": str(year),
                    "count": str(len(coverages)),
                    "coverage_mean": f"{sum(coverages) / len(coverages):.4f}",
                    "coverage_min": f"{min(coverages):.4f}",
                    "coverage_max": f"{max(coverages):.4f}",
                }
            )

    with COMPANY_REPORT.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["ticker", "count", "coverage_mean", "coverage_min", "coverage_max"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for ticker in sorted(company_buckets):
            coverages = company_buckets[ticker]
            writer.writerow(
                {
                    "ticker": ticker,
                    "count": str(len(coverages)),
                    "coverage_mean": f"{sum(coverages) / len(coverages):.4f}",
                    "coverage_min": f"{min(coverages):.4f}",
                    "coverage_max": f"{max(coverages):.4f}",
                }
            )


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
        _record_coverage(
            scope="single_year",
            formation_year=FORMATION_YEAR,
            ticker=ticker,
            status="GAP",
            coverage=None,
            valuation_score=None,
            quality_score=None,
            overall=None,
            missing="",
            note=str(exc),
        )
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

    _record_coverage(
        scope="single_year",
        formation_year=FORMATION_YEAR,
        ticker=ticker,
        status="OK",
        coverage=company.quality.coverage,
        valuation_score=company.valuation.score,
        quality_score=company.quality.score,
        overall=overall_score(company),
        missing=missing,
        note="",
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
            _record_coverage(
                scope="multi_year",
                formation_year=formation_year,
                ticker=ticker,
                status="GAP",
                coverage=None,
                valuation_score=None,
                quality_score=None,
                overall=None,
                missing="",
                note=str(exc),
            )
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

        _record_coverage(
            scope="multi_year",
            formation_year=formation_year,
            ticker=ticker,
            status="OK",
            coverage=company.quality.coverage,
            valuation_score=company.valuation.score,
            quality_score=company.quality.score,
            overall=overall_score(company),
            missing=missing,
            note="",
        )

        assert company.valuation.score >= 0
        assert company.quality.score >= 0
        assert overall_score(company) >= 0
        assert company.valuation.summary
        assert company.quality.summary
        processed += 1

    assert processed > 0, f"No companies could be scored for formation year {formation_year}"
