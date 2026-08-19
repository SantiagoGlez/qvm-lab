from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quantlab.strategies.qvm.backtest import contribution as contribution_backtest
from quantlab.strategies.qvm.models import AnalysisResult, Company, CompanyMetrics, ValuationFacts


def _make_company(ticker: str, valuation_score: float, quality_score: float, band: str) -> Company:
    company = Company(ticker=ticker)
    company.valuation = AnalysisResult(score=valuation_score)
    company.quality = AnalysisResult(score=quality_score, coverage=1.0)
    company.valuation_facts = ValuationFacts(used_pe_count=8, historical_percentile=0.25)
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
    company.valuation.valuation_band = band
    return company


class _FakePriceProvider:
    def __init__(self, price_map: dict[str, pd.Series]) -> None:
        self.price_map = price_map

    def __call__(self, ticker: str, start: date, end: date) -> pd.Series:
        return self.price_map[ticker.upper()]


def test_run_contribution_experiment_suite_writes_comparison_and_orders_strategies(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(contribution_backtest, "load_universe", lambda universe_path=None: ["AAA", "BBB", "CCC", "SPY"])

    def fake_score_universe_for_year(formation_year: int, tickers: list[str], valuation_repo=None, financial_repo=None) -> list[Company]:
        return [
            _make_company("AAA", valuation_score=95.0, quality_score=95.0, band="Very Expensive"),
            _make_company("BBB", valuation_score=88.0, quality_score=90.0, band="Cheap"),
            _make_company("CCC", valuation_score=82.0, quality_score=85.0, band="Fair Value"),
        ]

    monkeypatch.setattr(contribution_backtest, "score_universe_for_year", fake_score_universe_for_year)

    dates = pd.to_datetime(
        [
            "2025-04-01",
            "2025-06-01",
            "2025-08-01",
            "2025-10-01",
            "2025-12-01",
            "2026-02-01",
            "2026-04-01",
        ]
    )
    price_map = {
        "AAA": pd.Series([100.0, 104.0, 108.0, 112.0, 116.0, 120.0, 124.0], index=dates),
        "BBB": pd.Series([100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0], index=dates),
        "CCC": pd.Series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0], index=dates),
        "SPY": pd.Series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0], index=dates),
    }
    provider = _FakePriceProvider(price_map)

    suite = contribution_backtest.run_contribution_experiment_suite(
        [
            contribution_backtest.ContributionBacktestConfig(
                start_year=2025,
                end_year=2025,
                top_n=2,
                rebalance_month=4,
                rebalance_day=1,
                contribution_months=2,
                initial_contribution=100.0,
                contribution_amount=100.0,
                scoring_mode="quality",
                selection_policy="score",
                experiment_name="Quality Only + Contributions",
            ),
            contribution_backtest.ContributionBacktestConfig(
                start_year=2025,
                end_year=2025,
                top_n=2,
                rebalance_month=4,
                rebalance_day=1,
                contribution_months=2,
                initial_contribution=100.0,
                contribution_amount=100.0,
                scoring_mode="quality",
                selection_policy="action_simplified_relaxed_score_band",
                experiment_name="Action Simplified: Overall>=75 + Not Very Expensive + Contributions",
            ),
        ],
        output_dir=tmp_path,
        price_provider=provider,
    )

    assert suite.comparison_path.exists()
    comparison_df = pd.read_csv(suite.comparison_path)
    assert set(comparison_df["experiment"]) == {
        "Quality Only + Contributions",
        "Action Simplified: Overall>=75 + Not Very Expensive + Contributions",
    }
    assert {"twr_cagr", "mwrr", "benchmark_twr_cagr", "benchmark_mwrr"}.issubset(comparison_df.columns)

    quality_row = comparison_df.loc[comparison_df["experiment"] == "Quality Only + Contributions"].iloc[0]
    action_row = comparison_df.loc[
        comparison_df["experiment"] == "Action Simplified: Overall>=75 + Not Very Expensive + Contributions"
    ].iloc[0]

    assert quality_row["twr_cagr"] > action_row["twr_cagr"]
    assert quality_row["mwrr"] > action_row["mwrr"]

    quality_result = suite.run_results["Quality Only + Contributions"]
    assert quality_result.audit_path.exists()
    assert quality_result.returns_path.exists()
    assert quality_result.cashflows_path.exists()
    assert quality_result.selection_diagnostics_path.exists()

    returns_df = pd.read_csv(quality_result.returns_path)
    assert {"portfolio_return", "benchmark_return", "portfolio_mwrr", "benchmark_mwrr"}.issubset(returns_df.columns)
    assert returns_df.loc[0, "selected_count"] == 2
    assert returns_df.loc[0, "contribution_events"] == 6