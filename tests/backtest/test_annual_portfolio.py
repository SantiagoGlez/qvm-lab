from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quantlab.strategies.qvm.backtest import annual as annual_backtest
from quantlab.strategies.qvm.models import AnalysisResult, Company, CompanyMetrics, ReverseDCFAnalysis, ValuationFacts


def _make_company(
    ticker: str,
    valuation_score: float,
    quality_score: float,
    coverage: float = 1.0,
    intrinsic_assessment: str = "Unavailable",
    intrinsic_history_quality: str = "Unknown",
) -> Company:
    company = Company(ticker=ticker)
    company.valuation = AnalysisResult(score=valuation_score)
    company.quality = AnalysisResult(score=quality_score, coverage=coverage)
    company.valuation_facts = ValuationFacts(
        used_pe_count=8,
        historical_percentile=0.25,
    )
    company.metrics = CompanyMetrics(
        roic=0.20,
        roe=0.25,
        operating_margin=0.18,
        revenue_cagr=0.12,
        eps_cagr=0.16,
        fcf_margin=0.08,
        fcf_conversion=0.75,
        net_debt_ebitda=0.2,
        interest_coverage=8.0,
    )
    company.reverse_dcf = ReverseDCFAnalysis(
        assessment=intrinsic_assessment,
        history_quality=intrinsic_history_quality,
    )
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
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None, intrinsic_price_lookup=None: [
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
    assert result.selection_diagnostics_path.exists()
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

    diagnostics_df = pd.read_csv(result.selection_diagnostics_path)
    assert diagnostics_df.loc[0, "formation_year"] == 2025
    assert diagnostics_df.loc[0, "selected_n"] == 2
    assert diagnostics_df.loc[0, "universe_n"] == 3
    assert "val_median_spread" in diagnostics_df.columns
    assert "quality_median_spread" in diagnostics_df.columns
    assert "coverage_median_spread" in diagnostics_df.columns


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


def test_select_companies_soft_valuation_guard_uses_valuation_score() -> None:
    companies = [
        _make_company("Q1", valuation_score=90.0, quality_score=99.0),
        _make_company("Q2", valuation_score=10.0, quality_score=98.0),
        _make_company("Q3", valuation_score=85.0, quality_score=97.0),
        _make_company("Q4", valuation_score=15.0, quality_score=96.0),
        _make_company("Q5", valuation_score=80.0, quality_score=95.0),
    ]

    selected = annual_backtest.select_companies(
        companies,
        top_n=3,
        scoring_mode="quality",
        selection_policy="quality_soft_valuation_guard",
        quality_pool_size=4,
        valuation_guard_min_score=20.0,
    )

    assert [company.ticker for company in selected] == ["Q1", "Q3", "Q5"]


def test_select_companies_quality_cheapest_half_uses_valuation_score() -> None:
    companies = [
        _make_company("A", valuation_score=10.0, quality_score=100.0),
        _make_company("B", valuation_score=40.0, quality_score=99.0),
        _make_company("C", valuation_score=90.0, quality_score=98.0),
        _make_company("D", valuation_score=70.0, quality_score=97.0),
        _make_company("E", valuation_score=80.0, quality_score=96.0),
        _make_company("F", valuation_score=95.0, quality_score=95.0),
    ]

    selected = annual_backtest.select_companies(
        companies,
        top_n=3,
        scoring_mode="quality",
        selection_policy="quality_cheapest_half",
        quality_pool_size=5,
        valuation_guard_min_score=20.0,
    )

    assert [company.ticker for company in selected] == ["C", "E", "D"]


def test_select_companies_quality_hysteresis_preserves_protected_holdings() -> None:
    companies = [
        _make_company("A", valuation_score=90.0, quality_score=100.0),
        _make_company("B", valuation_score=85.0, quality_score=99.0),
        _make_company("C", valuation_score=80.0, quality_score=98.0),
        _make_company("D", valuation_score=75.0, quality_score=97.0),
        _make_company("E", valuation_score=70.0, quality_score=96.0),
        _make_company("F", valuation_score=65.0, quality_score=95.0),
        _make_company("G", valuation_score=60.0, quality_score=94.0),
    ]

    selected = annual_backtest.select_companies_quality_hysteresis(
        companies,
        {"A", "B", "C"},
        top_n=3,
        scoring_mode="quality",
        keep_top_n=5,
        min_gap=2.0,
    )

    assert [company.ticker for company in selected] == ["A", "B", "C"]

    selected_2 = annual_backtest.select_companies_quality_hysteresis(
        companies,
        {"A", "B"},
        top_n=3,
        scoring_mode="quality",
        keep_top_n=5,
        min_gap=2.0,
    )
    assert selected_2[0].ticker == "A"
    assert selected_2[1].ticker == "B"
    assert selected_2[2].ticker == "C"


def test_select_companies_portfolio_signal_filters_on_positive_action_buckets() -> None:
    companies = [
        _make_company("A", valuation_score=90.0, quality_score=100.0),
        _make_company("B", valuation_score=85.0, quality_score=99.0),
        _make_company("C", valuation_score=80.0, quality_score=98.0),
        _make_company("D", valuation_score=75.0, quality_score=97.0),
        _make_company("E", valuation_score=70.0, quality_score=96.0),
        _make_company("F", valuation_score=65.0, quality_score=95.0),
    ]

    for company in companies:
        company.portfolio.action = "Watch"
    companies[0].portfolio.action = "Add"
    companies[1].portfolio.action = "Keep"
    companies[2].portfolio.action = "Keep (Monitor)"
    companies[3].portfolio.action = "Watch"
    companies[4].portfolio.action = "Watch"
    companies[5].portfolio.action = "Exit"

    selected = annual_backtest.select_companies(
        companies,
        top_n=3,
        scoring_mode="quality",
        selection_policy="portfolio_signal",
        quality_pool_size=10,
        valuation_guard_min_score=0.0,
    )

    assert [company.ticker for company in selected] == ["A", "B", "C"]


def test_select_companies_action_simplified_strict_band_uses_overall_and_band() -> None:
    companies = [
        _make_company("A", valuation_score=90.0, quality_score=90.0),
        _make_company("B", valuation_score=80.0, quality_score=80.0),
        _make_company("C", valuation_score=88.0, quality_score=88.0),
        _make_company("D", valuation_score=70.0, quality_score=70.0),
    ]
    companies[0].valuation.valuation_band = "Fair Value"
    companies[1].valuation.valuation_band = "Very Expensive"
    companies[2].valuation.valuation_band = "Cheap"
    companies[3].valuation.valuation_band = "Deep Value"

    selected = annual_backtest.select_companies(
        companies,
        top_n=3,
        scoring_mode="quality",
        selection_policy="action_simplified_strict_band",
        quality_pool_size=20,
        valuation_guard_min_score=20.0,
    )

    assert [company.ticker for company in selected] == ["A", "C"]


def test_select_companies_action_simplified_relaxed_score_band_excludes_very_expensive() -> None:
    companies = [
        _make_company("A", valuation_score=82.0, quality_score=82.0),
        _make_company("B", valuation_score=78.0, quality_score=78.0),
        _make_company("C", valuation_score=95.0, quality_score=95.0),
    ]
    companies[0].valuation.valuation_band = "Expensive"
    companies[1].valuation.valuation_band = "Fair Value"
    companies[2].valuation.valuation_band = "Very Expensive"

    selected = annual_backtest.select_companies(
        companies,
        top_n=3,
        scoring_mode="quality",
        selection_policy="action_simplified_relaxed_score_band",
        quality_pool_size=20,
        valuation_guard_min_score=20.0,
    )

    assert [company.ticker for company in selected] == ["A", "B"]


def test_select_companies_quality_intrinsic_guard_filters_on_assessment_labels() -> None:
    companies = [
        _make_company("A", valuation_score=70.0, quality_score=95.0, intrinsic_assessment="Reasonable Expectations"),
        _make_company("B", valuation_score=70.0, quality_score=94.0, intrinsic_assessment="Optimistic Expectations"),
        _make_company("C", valuation_score=70.0, quality_score=93.0, intrinsic_assessment="Conservative Expectations"),
    ]

    selected = annual_backtest.select_companies(
        companies,
        top_n=3,
        scoring_mode="quality",
        selection_policy="quality_intrinsic_guard",
        quality_pool_size=20,
        valuation_guard_min_score=20.0,
        intrinsic_guard_allowed_assessments=(
            "Very Conservative Expectations",
            "Conservative Expectations",
            "Reasonable Expectations",
        ),
    )

    assert [company.ticker for company in selected] == ["A", "C"]


def test_select_companies_quality_intrinsic_tilt_reorders_close_quality_names() -> None:
    companies = [
        _make_company(
            "A",
            valuation_score=70.0,
            quality_score=90.0,
            intrinsic_assessment="Very Optimistic Expectations",
            intrinsic_history_quality="Stable",
        ),
        _make_company(
            "B",
            valuation_score=70.0,
            quality_score=89.0,
            intrinsic_assessment="Very Conservative Expectations",
            intrinsic_history_quality="Stable",
        ),
    ]

    selected = annual_backtest.select_companies(
        companies,
        top_n=2,
        scoring_mode="quality",
        selection_policy="quality_intrinsic_tilt",
        quality_pool_size=20,
        valuation_guard_min_score=20.0,
        intrinsic_tilt_weight=0.15,
        intrinsic_tilt_unavailable_score=50.0,
    )

    assert [company.ticker for company in selected] == ["B", "A"]


def test_select_companies_quality_intrinsic_hybrid_applies_guard_before_tilt() -> None:
    companies = [
        _make_company(
            "A",
            valuation_score=70.0,
            quality_score=91.0,
            intrinsic_assessment="Very Optimistic Expectations",
            intrinsic_history_quality="Stable",
        ),
        _make_company(
            "B",
            valuation_score=70.0,
            quality_score=90.0,
            intrinsic_assessment="Conservative Expectations",
            intrinsic_history_quality="Stable",
        ),
        _make_company(
            "C",
            valuation_score=70.0,
            quality_score=89.0,
            intrinsic_assessment="Reasonable Expectations",
            intrinsic_history_quality="Stable",
        ),
    ]

    selected = annual_backtest.select_companies(
        companies,
        top_n=3,
        scoring_mode="quality",
        selection_policy="quality_intrinsic_guard_tilt",
        quality_pool_size=20,
        valuation_guard_min_score=20.0,
        intrinsic_guard_allowed_assessments=(
            "Very Conservative Expectations",
            "Conservative Expectations",
            "Reasonable Expectations",
            "Optimistic Expectations",
        ),
        intrinsic_tilt_weight=0.10,
        intrinsic_tilt_unavailable_score=50.0,
    )

    assert [company.ticker for company in selected] == ["B", "C"]


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
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None, intrinsic_price_lookup=None: [
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


def test_score_universe_for_year_computes_reverse_dcf_when_price_lookup_present(monkeypatch) -> None:
    class _FakeValRepo:
        def load(self, ticker: str, formation_year: int) -> dict[str, object]:
            return {
                "ticker": ticker,
                "formation_year": formation_year,
                "historical_pe_values": [20.0, 22.0, 24.0],
                "historical_average_pe": 22.0,
                "historical_median_pe": 22.0,
                "historical_percentile": 0.5,
                "current_pe": 24.0,
                "used_pe_count": 3,
            }

    class _FakeFinRepo:
        def load(self, ticker: str, formation_year: int) -> dict[str, object]:
            return {
                "ticker": ticker,
                "formation_year": formation_year,
                "year": 2020,
                "revenue": 1300.0,
                "net_income": 200.0,
                "eps": 2.0,
                "operating_margin": 0.2,
                "cash": 100.0,
                "total_debt": 50.0,
                "total_assets": 500.0,
                "net_assets": 300.0,
                "shares_outstanding": 10.0,
                "free_cash_flow": 120.0,
                "revenue_cagr": 0.1,
                "revenue_cagr_years": 3,
                "eps_cagr": 0.1,
                "eps_cagr_years": 3,
                "revenue_by_year": {2015: 700.0, 2020: 1300.0},
                "eps_by_year": {2015: 1.0, 2020: 2.0},
                "fcf_by_year": {2015: 50.0, 2020: 120.0},
            }

    companies = annual_backtest.score_universe_for_year(
        2021,
        ["AAA"],
        valuation_repo=_FakeValRepo(),
        financial_repo=_FakeFinRepo(),
        intrinsic_price_lookup={"AAA": 100.0},
    )

    assert len(companies) == 1
    assert companies[0].reverse_dcf.assessment != "Unavailable"
    assert companies[0].reverse_dcf.implied_growth is not None


def test_run_annual_backtest_handles_missing_benchmark_history(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(annual_backtest, "load_universe", lambda universe_path=None: ["AAA"])
    monkeypatch.setattr(
        annual_backtest,
        "score_universe_for_year",
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None, intrinsic_price_lookup=None: [
            _make_company("AAA", 100.0, 90.0)
        ],
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
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None, intrinsic_price_lookup=None: [
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


def test_run_experiment_suite_preserves_quality_metric_exclusions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(annual_backtest, "load_universe", lambda universe_path=None: ["AAA"])

    def fake_score_company(ticker: str, valuation_data: dict[str, object], financial_data: dict[str, object]) -> Company:
        company = Company(
            ticker=ticker,
            metrics=CompanyMetrics(
                roic=0.20,
                roe=0.25,
                operating_margin=0.18,
                revenue_cagr=0.12,
                eps_cagr=0.16,
                fcf_margin=0.08,
                fcf_conversion=0.75,
                net_debt_ebitda=0.2,
                interest_coverage=8.0,
            ),
        )
        company.valuation = AnalysisResult(score=90.0)
        return company

    monkeypatch.setattr(
        annual_backtest,
        "score_universe_for_year",
        lambda formation_year, tickers, valuation_repo=None, financial_repo=None, intrinsic_price_lookup=None: [
            fake_score_company("AAA", {}, {}),
        ],
    )

    price_series = pd.Series(
        [100.0, 110.0],
        index=pd.to_datetime(["2025-04-01", "2026-04-01"]),
        name="price",
    )
    provider = _FakePriceProvider({"SPY": price_series, "AAA": price_series})

    result = annual_backtest.run_experiment_suite(
        configs=[
            annual_backtest.AnnualBacktestConfig(
                start_year=2025,
                end_year=2025,
                top_n=1,
                scoring_mode="quality",
                experiment_name="Q baseline",
                quality_metric_exclusions=("roic",),
            )
        ],
        output_dir=tmp_path,
        price_provider=provider,
    )

    audit_row = result.run_results["Q baseline"].audit_rows[0]
    expected = annual_backtest.analyse_quality(
        fake_score_company("AAA", {}, {}),
        excluded_metrics=("roic",),
    )
    assert float(audit_row["quality_score"]) == pytest.approx(expected.score)
    assert result.comparison_path.exists()
    comparison_df = pd.read_csv(result.comparison_path)
    assert comparison_df["experiment"].tolist() == ["Q baseline"]
    assert "cagr" in comparison_df.columns