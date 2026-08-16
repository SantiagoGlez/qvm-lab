from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quantlab.strategies.qvm.backtest import annual as annual_backtest
from quantlab.strategies.qvm.models import AnalysisResult, Company, CompanyMetrics, ValuationFacts


def _make_company(ticker: str, valuation_score: float, quality_score: float, coverage: float = 1.0) -> Company:
    company = Company(ticker=ticker)
    company.valuation = AnalysisResult(score=valuation_score)
    company.quality = AnalysisResult(score=quality_score, coverage=coverage)
    company.valuation_facts = ValuationFacts(
        used_pe_count=8,
        historical_percentile=0.25,
    )
    company.metrics = CompanyMetrics()
    return company


class _FakePriceProvider:
    def __init__(self, price_map: dict[str, pd.Series]) -> None:
        self.price_map = price_map

    def __call__(self, ticker: str, start: date, end: date) -> pd.Series:
        return self.price_map[ticker.upper()]


def test_run_annual_backtest_writes_audit_and_return_csvs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(annual_backtest, "load_universe", lambda universe_path=None: ["AAA", "BBB", "CCC"])

    def fake_score_company(ticker: str, valuation_data: dict[str, object], financial_data: dict[str, object]) -> Company:
        score_map = {
            "AAA": (95.0, 90.0),
            "BBB": (88.0, 84.0),
            "CCC": (70.0, 72.0),
        }
        valuation_score, quality_score = score_map[ticker]
        company = _make_company(ticker, valuation_score, quality_score, coverage=0.9)
        company.valuation_facts.used_pe_count = int(valuation_data["used_pe_count"])
        return company

    monkeypatch.setattr(
        annual_backtest,
        "score_universe_for_year",
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None: [
            fake_score_company("AAA", {"used_pe_count": 8}, {}),
            fake_score_company("BBB", {"used_pe_count": 8}, {}),
            fake_score_company("CCC", {"used_pe_count": 8}, {}),
        ],
    )

    price_series = pd.Series(
        [100.0, 110.0, 120.0],
        index=pd.to_datetime(["2025-04-01", "2026-04-01", "2026-04-02"]),
        name="price",
    )
    provider = _FakePriceProvider({"SPY": price_series, "AAA": price_series, "BBB": price_series, "CCC": price_series})

    result = annual_backtest.run_annual_backtest(
        annual_backtest.AnnualBacktestConfig(
            start_year=2025,
            end_year=2025,
            output_dir=tmp_path,
            top_n=2,
        ),
        price_provider=provider,
    )

    assert result.audit_path.exists()
    assert result.returns_path.exists()
    assert result.summary.years == 1
    assert result.year_results[0].selected_count == 2
    assert result.year_results[0].benchmark_return == pytest.approx(0.1)
    assert result.year_results[0].portfolio_return == pytest.approx(0.1)

    audit_df = pd.read_csv(result.audit_path)
    assert audit_df["rank"].tolist() == [1, 2]
    assert audit_df["ticker"].tolist() == ["AAA", "BBB"]
    assert "annual_return" in audit_df.columns

    returns_df = pd.read_csv(result.returns_path)
    assert returns_df.loc[0, "portfolio_return"] == pytest.approx(0.1)
    assert returns_df.loc[0, "benchmark_return"] == pytest.approx(0.1)


def test_rank_companies_prefers_higher_overall_score() -> None:
    ranked = annual_backtest.rank_companies(
        [
            _make_company("CCC", 70.0, 72.0),
            _make_company("AAA", 95.0, 90.0),
            _make_company("BBB", 88.0, 84.0),
        ],
        top_n=3,
    )

    assert [company.ticker for company in ranked] == ["AAA", "BBB", "CCC"]


def test_rank_companies_with_mode_supports_quality_and_valuation() -> None:
    companies = [
        _make_company("AAA", valuation_score=95.0, quality_score=20.0),
        _make_company("BBB", valuation_score=60.0, quality_score=90.0),
        _make_company("CCC", valuation_score=70.0, quality_score=70.0),
    ]

    by_quality = annual_backtest.rank_companies_with_mode(companies, top_n=3, scoring_mode="quality")
    by_valuation = annual_backtest.rank_companies_with_mode(companies, top_n=3, scoring_mode="valuation")

    assert [company.ticker for company in by_quality] == ["BBB", "CCC", "AAA"]
    assert [company.ticker for company in by_valuation] == ["AAA", "CCC", "BBB"]


def test_compute_average_turnover() -> None:
    turnover = annual_backtest._compute_average_turnover(
        [
            {"A", "B", "C"},
            {"B", "C", "D"},
            {"B", "D", "E"},
        ],
        top_n=3,
    )
    assert turnover == pytest.approx(2 / 6)


def test_run_experiment_suite_writes_comparison_csv(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(annual_backtest, "load_universe", lambda universe_path=None: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(
        annual_backtest,
        "score_universe_for_year",
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None: [
            _make_company("AAA", 90.0, 70.0),
            _make_company("BBB", 80.0, 80.0),
            _make_company("CCC", 70.0, 90.0),
        ],
    )

    price_series = pd.Series(
        [100.0, 110.0],
        index=pd.to_datetime(["2025-04-01", "2026-04-01"]),
        name="price",
    )
    provider = _FakePriceProvider({"SPY": price_series, "AAA": price_series, "BBB": price_series, "CCC": price_series})

    suite = annual_backtest.run_experiment_suite(
        configs=[
            annual_backtest.AnnualBacktestConfig(
                start_year=2025,
                end_year=2025,
                top_n=2,
                scoring_mode="qv",
                experiment_name="QV",
            ),
            annual_backtest.AnnualBacktestConfig(
                start_year=2025,
                end_year=2025,
                top_n=2,
                scoring_mode="quality",
                experiment_name="Q",
            ),
        ],
        output_dir=tmp_path,
        price_provider=provider,
    )

    assert suite.comparison_path.exists()
    table = pd.read_csv(suite.comparison_path)
    assert table["experiment"].tolist() == ["QV", "Q"]
    assert "sharpe" in table.columns
    assert "max_drawdown" in table.columns
    assert "turnover" in table.columns


def test_quality_battle_test_configs_include_requested_dimensions() -> None:
    configs = annual_backtest._quality_battle_test_configs(start_year=2015, end_year=2025, top_n=10)
    names = [config.experiment_name for config in configs]

    assert "Q baseline" in names
    assert "Q window 2015-2018" in names
    assert "Q window 2019-2022" in names
    assert "Q window 2023-2025" in names
    assert "Q rebalance month 01" in names
    assert "Q rebalance month 04" in names
    assert "Q rebalance month 07" in names
    assert "Q rebalance month 10" in names
    assert "Q top 5" in names
    assert "Q top 10" in names
    assert "Q top 15" in names
    assert "Q top 20" in names


def test_run_annual_backtest_handles_missing_benchmark_history(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(annual_backtest, "load_universe", lambda universe_path=None: ["AAA"])
    monkeypatch.setattr(
        annual_backtest,
        "score_universe_for_year",
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None: [_make_company("AAA", 100.0, 90.0)],
    )

    empty_series = pd.Series(dtype=float, name="SPY")
    price_series = pd.Series(
        [100.0, 110.0],
        index=pd.to_datetime(["2025-04-01", "2026-04-01"]),
        name="AAA",
    )
    def fake_provider(ticker: str, start: date, end: date) -> pd.Series:
        if ticker == "SPY":
            return empty_series
        return price_series

    result = annual_backtest.run_annual_backtest(
        annual_backtest.AnnualBacktestConfig(
            start_year=2025,
            end_year=2025,
            top_n=1,
            formation_month=4,
            formation_day=1,
            output_dir=tmp_path,
            benchmark_ticker="SPY",
            scoring_mode="quality",
        ),
        price_provider=fake_provider,
    )

    assert result.summary.years == 1
    assert result.year_results[0].benchmark_return == 0.0
    assert result.year_results[0].portfolio_return > 0.0


def test_run_leave_one_year_out_quality_writes_csv(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(annual_backtest, "load_universe", lambda universe_path=None: ["AAA", "BBB"])
    monkeypatch.setattr(
        annual_backtest,
        "score_universe_for_year",
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None: [
            _make_company("AAA", 80.0, 90.0),
            _make_company("BBB", 70.0, 85.0),
        ],
    )

    price_series = pd.Series(
        [100.0, 110.0, 121.0],
        index=pd.to_datetime(["2025-04-01", "2026-04-01", "2027-04-03"]),
        name="price",
    )
    provider = _FakePriceProvider({"SPY": price_series, "AAA": price_series, "BBB": price_series})

    rows, output_path = annual_backtest.run_leave_one_year_out_quality(
        start_year=2025,
        end_year=2026,
        top_n=2,
        output_dir=tmp_path,
        price_provider=provider,
    )

    assert output_path.exists()
    assert len(rows) == 2
    df = pd.read_csv(output_path)
    assert sorted(df["omitted_year"].tolist()) == [2025, 2026]
    assert "cagr" in df.columns