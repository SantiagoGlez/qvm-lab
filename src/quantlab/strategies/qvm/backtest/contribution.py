from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..analysis.quality import analyse_quality, quality_eligible
from ..models import Company
from .annual import (
    AnnualBacktestConfig,
    build_audit_row,
    build_selection_diagnostics_row,
    score_universe_for_year,
    select_companies,
)
from .common import (
    AdjustedCloseProvider,
    DEFAULT_CONTRIBUTION_OUTPUT_DIR,
    YahooAdjustedCloseProvider,
    _price_on_or_after,
    _write_csv,
    formation_date,
    iter_contribution_dates,
    load_universe,
    xirr,
)


@dataclass(slots=True)
class ContributionBacktestConfig:
    start_year: int = 2015
    end_year: int = 2025
    rebalance_month: int = 4
    rebalance_day: int = 1
    contribution_months: int = 2
    initial_contribution: float = 1.0
    contribution_amount: float = 1.0
    top_n: int = 10
    universe_path: Path | None = None
    output_dir: Path | None = None
    benchmark_ticker: str = "SPY"
    scoring_mode: str = "quality"
    selection_policy: str = "score"
    experiment_name: str = "Quality Only + Contributions"
    quality_metric_exclusions: tuple[str, ...] = ()
    quality_pool_size: int = 20
    valuation_guard_min_score: float = 20.0


@dataclass(slots=True)
class ContributionBacktestPeriodResult:
    formation_year: int
    period_start: date
    period_end: date
    selected_count: int
    contribution_events: int
    total_contributions: float
    portfolio_return: float
    benchmark_return: float
    excess_return: float
    portfolio_mwrr: float
    benchmark_mwrr: float
    final_value: float
    benchmark_final_value: float


@dataclass(slots=True)
class ContributionBacktestSummary:
    years: int
    periods: int
    total_contributions: float
    portfolio_twr_cagr: float
    benchmark_twr_cagr: float
    excess_twr_cagr: float
    portfolio_mwrr: float
    benchmark_mwrr: float
    excess_mwrr: float
    portfolio_total_return: float
    benchmark_total_return: float
    final_value: float
    benchmark_final_value: float
    win_rate: float


@dataclass(slots=True)
class ContributionBacktestRunResult:
    audit_path: Path
    returns_path: Path
    cashflows_path: Path
    selection_diagnostics_path: Path
    audit_rows: list[dict[str, object]]
    period_results: list[ContributionBacktestPeriodResult]
    summary: ContributionBacktestSummary


@dataclass(slots=True)
class ContributionExperimentComparisonRow:
    experiment: str
    scoring_mode: str
    selection_policy: str
    rebalance_month: int
    rebalance_day: int
    contribution_months: int
    top_n: int
    years: int
    twr_cagr: float
    benchmark_twr_cagr: float
    excess_twr_cagr: float
    mwrr: float
    benchmark_mwrr: float
    excess_mwrr: float
    total_contributions: float
    final_value: float
    benchmark_final_value: float
    win_rate: float


@dataclass(slots=True)
class ContributionExperimentSuiteResult:
    rows: list[ContributionExperimentComparisonRow]
    comparison_path: Path
    run_results: dict[str, ContributionBacktestRunResult]


def _price_at_date(series: pd.Series, target: date) -> float:
    _, price = _price_on_or_after(series, target)
    return price


def _value_of_holdings(shares: dict[str, float], price_cache: dict[str, pd.Series], target: date) -> float:
    total = 0.0
    for ticker, share_count in shares.items():
        if share_count == 0:
            continue
        series = price_cache.get(ticker, pd.Series(dtype=float))
        if series.empty:
            continue
        total += share_count * _price_at_date(series, target)
    return total


def _buy_equal_weighted(
    shares: dict[str, float],
    price_cache: dict[str, pd.Series],
    target: date,
    investment: float,
) -> None:
    if investment <= 0 or not shares:
        return

    per_holding = investment / len(shares)
    for ticker in shares:
        series = price_cache.get(ticker, pd.Series(dtype=float))
        if series.empty:
            continue
        price = _price_at_date(series, target)
        if price > 0:
            shares[ticker] += per_holding / price


def _build_contribution_config(config: ContributionBacktestConfig) -> AnnualBacktestConfig:
    return AnnualBacktestConfig(
        start_year=config.start_year,
        end_year=config.end_year,
        formation_month=config.rebalance_month,
        formation_day=config.rebalance_day,
        top_n=config.top_n,
        universe_path=config.universe_path,
        benchmark_ticker=config.benchmark_ticker,
        scoring_mode=config.scoring_mode,
        selection_policy=config.selection_policy,
        experiment_name=config.experiment_name,
        quality_metric_exclusions=config.quality_metric_exclusions,
        quality_pool_size=config.quality_pool_size,
        valuation_guard_min_score=config.valuation_guard_min_score,
    )


def _build_contribution_comparison_row(
    config: ContributionBacktestConfig,
    result: ContributionBacktestRunResult,
) -> ContributionExperimentComparisonRow:
    return ContributionExperimentComparisonRow(
        experiment=config.experiment_name,
        scoring_mode=config.scoring_mode,
        selection_policy=config.selection_policy,
        rebalance_month=config.rebalance_month,
        rebalance_day=config.rebalance_day,
        contribution_months=config.contribution_months,
        top_n=config.top_n,
        years=result.summary.years,
        twr_cagr=result.summary.portfolio_twr_cagr,
        benchmark_twr_cagr=result.summary.benchmark_twr_cagr,
        excess_twr_cagr=result.summary.excess_twr_cagr,
        mwrr=result.summary.portfolio_mwrr,
        benchmark_mwrr=result.summary.benchmark_mwrr,
        excess_mwrr=result.summary.excess_mwrr,
        total_contributions=result.summary.total_contributions,
        final_value=result.summary.final_value,
        benchmark_final_value=result.summary.benchmark_final_value,
        win_rate=result.summary.win_rate,
    )


def _final_cash_flow(cash_flows: list[tuple[date, float]], final_date: date, final_value: float) -> list[tuple[date, float]]:
    ordered = list(cash_flows)
    ordered.append((final_date, final_value))
    return ordered


def run_contribution_backtest(
    config: ContributionBacktestConfig,
    price_provider: AdjustedCloseProvider | None = None,
) -> ContributionBacktestRunResult:
    price_provider = price_provider or YahooAdjustedCloseProvider()
    universe = load_universe(config.universe_path)
    output_dir = config.output_dir or DEFAULT_CONTRIBUTION_OUTPUT_DIR

    period_starts = [formation_date(year, config.rebalance_month, config.rebalance_day) for year in range(config.start_year, config.end_year + 1)]
    period_ends = [formation_date(year + 1, config.rebalance_month, config.rebalance_day) for year in range(config.start_year, config.end_year + 1)]
    coverage_start = min(period_starts)
    coverage_end = max(period_ends) + timedelta(days=15)

    benchmark_series = price_provider(config.benchmark_ticker, coverage_start, coverage_end)
    price_cache = {ticker: price_provider(ticker, coverage_start, coverage_end) for ticker in universe}

    annual_selections: dict[int, tuple[list[Company], list[Company]]] = {}
    for formation_year in range(config.start_year, config.end_year + 1):
        companies = score_universe_for_year(formation_year, universe)
        for company in companies:
            company.quality = analyse_quality(company, excluded_metrics=config.quality_metric_exclusions)
        eligible_companies = [company for company in companies if quality_eligible(company)]
        selected_companies = select_companies(
            eligible_companies,
            top_n=config.top_n,
            scoring_mode=config.scoring_mode,
            selection_policy=config.selection_policy,
            quality_pool_size=config.quality_pool_size,
            valuation_guard_min_score=config.valuation_guard_min_score,
        )
        annual_selections[formation_year] = (eligible_companies, selected_companies)

    audit_rows: list[dict[str, object]] = []
    selection_diagnostics_rows: list[dict[str, object]] = []
    period_rows: list[dict[str, object]] = []
    cashflow_rows: list[dict[str, object]] = []
    period_results: list[ContributionBacktestPeriodResult] = []

    portfolio_shares: dict[str, float] = {}
    portfolio_cash_balance = 0.0
    benchmark_units = 0.0
    benchmark_cash_balance = 0.0
    all_portfolio_cash_flows: list[tuple[date, float]] = []
    all_benchmark_cash_flows: list[tuple[date, float]] = []
    total_contributions = 0.0
    win_count = 0

    for formation_year in range(config.start_year, config.end_year + 1):
        period_start = formation_date(formation_year, config.rebalance_month, config.rebalance_day)
        period_end = formation_date(formation_year + 1, config.rebalance_month, config.rebalance_day)
        contribution_dates = iter_contribution_dates(period_start, period_end, config.contribution_months)
        if not contribution_dates:
            continue

        eligible_companies, selected_companies = annual_selections[formation_year]
        selected_companies = [company for company in selected_companies if not price_cache.get(company.ticker, pd.Series(dtype=float)).empty]
        eligible_companies = [company for company in eligible_companies if not price_cache.get(company.ticker, pd.Series(dtype=float)).empty]

        selected_tickers = [company.ticker for company in selected_companies]
        if formation_year == config.start_year:
            portfolio_cash_balance = 0.0
            benchmark_cash_balance = 0.0
        else:
            portfolio_cash_balance = _value_of_holdings(portfolio_shares, price_cache, period_start)

        portfolio_shares = {ticker: 0.0 for ticker in selected_tickers}

        audit_rows.extend(
            build_audit_row(
                formation_year=formation_year,
                rank=rank,
                company=company,
                buy_date=period_start,
                buy_price=_price_at_date(price_cache[company.ticker], period_start),
                sell_date=period_end,
                sell_price=_price_at_date(price_cache[company.ticker], period_end),
            )
            for rank, company in enumerate(selected_companies, start=1)
        )

        selection_diagnostics_rows.append(
            build_selection_diagnostics_row(
                formation_year=formation_year,
                eligible_companies=eligible_companies,
                selected_companies=selected_companies,
            )
        )

        year_portfolio_growth = 1.0
        year_benchmark_growth = 1.0
        year_portfolio_cash_flows: list[tuple[date, float]] = []
        year_benchmark_cash_flows: list[tuple[date, float]] = []
        year_total_contributions = 0.0
        year_end_value = 0.0
        year_benchmark_end_value = 0.0

        for idx, contribution_date in enumerate(contribution_dates):
            contribution_value = config.initial_contribution if formation_year == config.start_year and idx == 0 else config.contribution_amount
            total_contributions += contribution_value
            year_total_contributions += contribution_value
            all_portfolio_cash_flows.append((contribution_date, -contribution_value))
            all_benchmark_cash_flows.append((contribution_date, -contribution_value))
            year_portfolio_cash_flows.append((contribution_date, -contribution_value))
            year_benchmark_cash_flows.append((contribution_date, -contribution_value))

            portfolio_value_before = portfolio_cash_balance + _value_of_holdings(portfolio_shares, price_cache, contribution_date)
            benchmark_value_before = benchmark_cash_balance + (benchmark_units * _price_at_date(benchmark_series, contribution_date) if not benchmark_series.empty else 0.0)

            portfolio_value_after_contribution = portfolio_value_before + contribution_value
            benchmark_value_after_contribution = benchmark_value_before + contribution_value

            if selected_tickers:
                portfolio_cash_balance = 0.0
                portfolio_shares = {ticker: 0.0 for ticker in selected_tickers}
                _buy_equal_weighted(portfolio_shares, price_cache, contribution_date, portfolio_value_after_contribution)
            else:
                portfolio_shares = {}
                portfolio_cash_balance = portfolio_value_after_contribution

            if not benchmark_series.empty and benchmark_value_after_contribution > 0:
                benchmark_units = benchmark_value_after_contribution / _price_at_date(benchmark_series, contribution_date)
                benchmark_cash_balance = 0.0
            else:
                benchmark_cash_balance = benchmark_value_after_contribution

            next_date = contribution_dates[idx + 1] if idx + 1 < len(contribution_dates) else period_end
            portfolio_end_value = portfolio_cash_balance + _value_of_holdings(portfolio_shares, price_cache, next_date)
            benchmark_end_value = benchmark_cash_balance + (benchmark_units * _price_at_date(benchmark_series, next_date) if not benchmark_series.empty else 0.0)

            portfolio_return = (portfolio_end_value / portfolio_value_after_contribution) - 1.0 if portfolio_value_after_contribution > 0 else 0.0
            benchmark_return = (benchmark_end_value / benchmark_value_after_contribution) - 1.0 if benchmark_value_after_contribution > 0 else 0.0

            year_portfolio_growth *= 1.0 + portfolio_return
            year_benchmark_growth *= 1.0 + benchmark_return
            year_end_value = portfolio_end_value
            year_benchmark_end_value = benchmark_end_value

            cashflow_rows.append(
                {
                    "formation_year": formation_year,
                    "contribution_date": contribution_date.isoformat(),
                    "contribution_value": round(contribution_value, 4),
                    "portfolio_value_before": round(portfolio_value_before, 4),
                    "portfolio_value_after_contribution": round(portfolio_value_after_contribution, 4),
                    "portfolio_value_end": round(portfolio_end_value, 4),
                    "benchmark_value_before": round(benchmark_value_before, 4),
                    "benchmark_value_after_contribution": round(benchmark_value_after_contribution, 4),
                    "benchmark_value_end": round(benchmark_end_value, 4),
                }
            )

        if year_portfolio_growth > year_benchmark_growth:
            win_count += 1

        if formation_year == config.end_year:
            all_portfolio_cash_flows.append((period_end, year_end_value))
            all_benchmark_cash_flows.append((period_end, year_benchmark_end_value))

        period_results.append(
            ContributionBacktestPeriodResult(
                formation_year=formation_year,
                period_start=period_start,
                period_end=period_end,
                selected_count=len(selected_companies),
                contribution_events=len(contribution_dates),
                total_contributions=round(year_total_contributions, 4),
                portfolio_return=year_portfolio_growth - 1.0,
                benchmark_return=year_benchmark_growth - 1.0,
                excess_return=year_portfolio_growth - year_benchmark_growth,
                portfolio_mwrr=xirr(year_portfolio_cash_flows + [(period_end, year_end_value)]),
                benchmark_mwrr=xirr(year_benchmark_cash_flows + [(period_end, year_benchmark_end_value)]),
                final_value=year_end_value,
                benchmark_final_value=year_benchmark_end_value,
            )
        )

        period_rows.append(
            {
                "formation_year": formation_year,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "selected_count": len(selected_companies),
                "contribution_events": len(contribution_dates),
                "total_contributions": round(year_total_contributions, 4),
                "portfolio_return": round(year_portfolio_growth - 1.0, 4),
                "benchmark_return": round(year_benchmark_growth - 1.0, 4),
                "excess_return": round((year_portfolio_growth - 1.0) - (year_benchmark_growth - 1.0), 4),
                "portfolio_end_value": round(year_end_value, 4),
                "benchmark_end_value": round(year_benchmark_end_value, 4),
                "portfolio_mwrr": round(xirr(year_portfolio_cash_flows + [(period_end, year_end_value)]), 4),
                "benchmark_mwrr": round(xirr(year_benchmark_cash_flows + [(period_end, year_benchmark_end_value)]), 4),
            }
        )

    portfolio_growth = 1.0
    benchmark_growth = 1.0
    for row in period_results:
        portfolio_growth *= 1.0 + row.portfolio_return
        benchmark_growth *= 1.0 + row.benchmark_return

    years = len(period_results)
    portfolio_mwrr = xirr(all_portfolio_cash_flows)
    benchmark_mwrr = xirr(all_benchmark_cash_flows)
    summary = ContributionBacktestSummary(
        years=years,
        periods=len(period_rows),
        total_contributions=total_contributions,
        portfolio_twr_cagr=portfolio_growth ** (1.0 / years) - 1.0 if years else 0.0,
        benchmark_twr_cagr=benchmark_growth ** (1.0 / years) - 1.0 if years else 0.0,
        excess_twr_cagr=(portfolio_growth ** (1.0 / years) - 1.0) - (benchmark_growth ** (1.0 / years) - 1.0) if years else 0.0,
        portfolio_mwrr=portfolio_mwrr,
        benchmark_mwrr=benchmark_mwrr,
        excess_mwrr=portfolio_mwrr - benchmark_mwrr,
        portfolio_total_return=portfolio_growth - 1.0,
        benchmark_total_return=benchmark_growth - 1.0,
        final_value=period_results[-1].final_value if period_results else 0.0,
        benchmark_final_value=period_results[-1].benchmark_final_value if period_results else 0.0,
        win_rate=(win_count / len(period_rows)) if period_rows else 0.0,
    )

    audit_path = output_dir / "audit.csv"
    returns_path = output_dir / "returns.csv"
    cashflows_path = output_dir / "cashflows.csv"
    selection_diagnostics_path = output_dir / "selection_diagnostics.csv"

    _write_csv(
        audit_path,
        audit_rows,
        [
            "formation_year",
            "rank",
            "ticker",
            "overall_score",
            "valuation_score",
            "quality_score",
            "quality_coverage",
            "missing_metrics",
            "historical_pe_observations_used",
            "valuation_percentile",
            "buy_date",
            "buy_price",
            "sell_date",
            "sell_price",
            "annual_return",
        ],
    )
    _write_csv(
        returns_path,
        period_rows,
        [
            "formation_year",
            "period_start",
            "period_end",
            "selected_count",
            "contribution_events",
            "total_contributions",
            "portfolio_return",
            "benchmark_return",
            "excess_return",
            "portfolio_end_value",
            "benchmark_end_value",
            "portfolio_mwrr",
            "benchmark_mwrr",
        ],
    )
    _write_csv(
        cashflows_path,
        cashflow_rows,
        [
            "formation_year",
            "contribution_date",
            "contribution_value",
            "portfolio_value_before",
            "portfolio_value_after_contribution",
            "portfolio_value_end",
            "benchmark_value_before",
            "benchmark_value_after_contribution",
            "benchmark_value_end",
        ],
    )
    _write_csv(
        selection_diagnostics_path,
        selection_diagnostics_rows,
        [
            "formation_year",
            "universe_n",
            "selected_n",
            "universe_val_median",
            "selected_val_median",
            "val_median_spread",
            "selected_val_median_pct_in_universe",
            "universe_expensive_share",
            "selected_expensive_share",
            "expensive_share_spread",
            "universe_cheap_share",
            "selected_cheap_share",
            "cheap_share_spread",
            "universe_quality_median",
            "selected_quality_median",
            "quality_median_spread",
            "universe_coverage_median",
            "selected_coverage_median",
            "coverage_median_spread",
        ],
    )

    return ContributionBacktestRunResult(
        audit_path=audit_path,
        returns_path=returns_path,
        cashflows_path=cashflows_path,
        selection_diagnostics_path=selection_diagnostics_path,
        audit_rows=audit_rows,
        period_results=period_results,
        summary=summary,
    )


def build_contribution_experiment_suite_row(
    config: ContributionBacktestConfig,
    result: ContributionBacktestRunResult,
) -> ContributionExperimentComparisonRow:
    return _build_contribution_comparison_row(config, result)


def run_contribution_experiment_suite(
    configs: list[ContributionBacktestConfig],
    output_dir: Path,
    price_provider: AdjustedCloseProvider | None = None,
) -> ContributionExperimentSuiteResult:
    price_provider = price_provider or YahooAdjustedCloseProvider()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[ContributionExperimentComparisonRow] = []
    run_results: dict[str, ContributionBacktestRunResult] = {}

    for config in configs:
        experiment_dir_name = config.experiment_name.lower().replace(" ", "_").replace("/", "_")
        experiment_output_dir = output_dir / experiment_dir_name
        run_result = run_contribution_backtest(
            ContributionBacktestConfig(
                start_year=config.start_year,
                end_year=config.end_year,
                rebalance_month=config.rebalance_month,
                rebalance_day=config.rebalance_day,
                contribution_months=config.contribution_months,
                initial_contribution=config.initial_contribution,
                contribution_amount=config.contribution_amount,
                top_n=config.top_n,
                universe_path=config.universe_path,
                output_dir=experiment_output_dir,
                benchmark_ticker=config.benchmark_ticker,
                scoring_mode=config.scoring_mode,
                selection_policy=config.selection_policy,
                experiment_name=config.experiment_name,
                quality_metric_exclusions=config.quality_metric_exclusions,
                quality_pool_size=config.quality_pool_size,
                valuation_guard_min_score=config.valuation_guard_min_score,
            ),
            price_provider=price_provider,
        )
        run_results[config.experiment_name] = run_result
        rows.append(build_contribution_experiment_suite_row(config, run_result))

    comparison_path = output_dir / "contribution_experiment_comparison.csv"
    comparison_rows = [
        {
            "experiment": row.experiment,
            "scoring_mode": row.scoring_mode,
            "selection_policy": row.selection_policy,
            "rebalance_month": row.rebalance_month,
            "rebalance_day": row.rebalance_day,
            "contribution_months": row.contribution_months,
            "top_n": row.top_n,
            "years": row.years,
            "twr_cagr": round(row.twr_cagr, 4),
            "benchmark_twr_cagr": round(row.benchmark_twr_cagr, 4),
            "excess_twr_cagr": round(row.excess_twr_cagr, 4),
            "mwrr": round(row.mwrr, 4),
            "benchmark_mwrr": round(row.benchmark_mwrr, 4),
            "excess_mwrr": round(row.excess_mwrr, 4),
            "total_contributions": round(row.total_contributions, 4),
            "final_value": round(row.final_value, 4),
            "benchmark_final_value": round(row.benchmark_final_value, 4),
            "win_rate": round(row.win_rate, 4),
        }
        for row in rows
    ]
    _write_csv(
        comparison_path,
        comparison_rows,
        [
            "experiment",
            "scoring_mode",
            "selection_policy",
            "rebalance_month",
            "rebalance_day",
            "contribution_months",
            "top_n",
            "years",
            "twr_cagr",
            "benchmark_twr_cagr",
            "excess_twr_cagr",
            "mwrr",
            "benchmark_mwrr",
            "excess_mwrr",
            "total_contributions",
            "final_value",
            "benchmark_final_value",
            "win_rate",
        ],
    )

    return ContributionExperimentSuiteResult(rows=rows, comparison_path=comparison_path, run_results=run_results)