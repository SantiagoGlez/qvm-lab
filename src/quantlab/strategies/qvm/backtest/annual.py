from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol
import csv

import pandas as pd
import yfinance as yf

from ..analysis.overall import overall_score
from ..analysis.quality import analyse_quality
from ..analysis.scoring import calculate_score
from ..historical.adapters import HistoricalQualityAdapter, HistoricalValuationAdapter
from ..historical.repositories import (
    CompaniesMarketCapHistoricalFinancialRepository,
    CompaniesMarketCapHistoricalValuationRepository,
)
from ..models import Company
from ..ticker_aliases import YAHOO_TICKER_MAP


REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_UNIVERSE_PATH = REPO_ROOT / "data" / "qvm" / "companies.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "qvm" / "backtest" / "annual_portfolio"


class AdjustedCloseProvider(Protocol):
    def __call__(self, ticker: str, start: date, end: date) -> pd.Series:
        raise NotImplementedError


@dataclass(slots=True)
class AnnualBacktestConfig:
    start_year: int = 2015
    end_year: int = 2025
    formation_month: int = 4
    formation_day: int = 1
    top_n: int = 10
    universe_path: Path | None = None
    output_dir: Path | None = None
    benchmark_ticker: str = "SPY"
    scoring_mode: str = "qv"
    experiment_name: str = "QV (baseline)"
    quality_metric_exclusions: tuple[str, ...] = ()


@dataclass(slots=True)
class AnnualBacktestYearResult:
    formation_year: int
    buy_date: date
    sell_date: date
    portfolio_return: float
    benchmark_return: float
    excess_return: float
    selected_count: int


@dataclass(slots=True)
class AnnualBacktestSummary:
    years: int
    portfolio_cagr: float
    benchmark_cagr: float
    excess_cagr: float
    win_rate: float
    cumulative_portfolio_return: float
    cumulative_benchmark_return: float
    portfolio_sharpe: float
    benchmark_sharpe: float
    portfolio_max_drawdown: float
    benchmark_max_drawdown: float
    turnover: float


@dataclass(slots=True)
class ExperimentComparisonRow:
    experiment: str
    scoring_mode: str
    formation_month: int
    formation_day: int
    top_n: int
    years: int
    cagr: float
    sharpe: float
    max_drawdown: float
    turnover: float
    win_rate_vs_spy: float
    spy_cagr: float
    excess_cagr: float


@dataclass(slots=True)
class ExperimentSuiteResult:
    rows: list[ExperimentComparisonRow]
    comparison_path: Path
    run_results: dict[str, AnnualBacktestRunResult]


@dataclass(slots=True)
class LeaveOneYearOutRow:
    omitted_year: int
    years: int
    cagr: float
    sharpe: float
    max_drawdown: float
    turnover: float
    win_rate_vs_spy: float
    spy_cagr: float
    excess_cagr: float


@dataclass(slots=True)
class QualityBattleTestResult:
    experiment_suite: ExperimentSuiteResult
    leave_one_year_out_path: Path
    leave_one_year_out_rows: list[LeaveOneYearOutRow]


@dataclass(slots=True)
class AnnualBacktestRunResult:
    audit_path: Path
    returns_path: Path
    audit_rows: list[dict[str, object]]
    year_results: list[AnnualBacktestYearResult]
    summary: AnnualBacktestSummary


class YahooAdjustedCloseProvider:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], pd.Series] = {}

    def __call__(self, ticker: str, start: date, end: date) -> pd.Series:
        canonical_ticker = ticker.upper()
        yf_ticker = YAHOO_TICKER_MAP.get(canonical_ticker, canonical_ticker)
        cache_key = (canonical_ticker, start.isoformat(), end.isoformat())
        if cache_key in self._cache:
            return self._cache[cache_key]

        end_with_buffer = end + timedelta(days=10)
        frame = yf.download(
            yf_ticker,
            start=start.isoformat(),
            end=end_with_buffer.isoformat(),
            auto_adjust=True,
            progress=False,
        )

        if frame.empty:
            series = pd.Series(dtype=float, name=canonical_ticker)
            self._cache[cache_key] = series
            return series

        close = frame["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close.index = pd.to_datetime(close.index).tz_localize(None)
        series = close.dropna().sort_index().astype(float)
        series.name = canonical_ticker
        self._cache[cache_key] = series
        return series


def load_universe(universe_path: Path | None = None) -> list[str]:
    path = universe_path or DEFAULT_UNIVERSE_PATH
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")

    df = pd.read_csv(path, dtype=str)
    tickers = [str(value).strip().upper() for value in df.get("ticker", pd.Series(dtype=str)).tolist()]
    return [ticker for ticker in tickers if ticker]


def formation_date(year: int, month: int, day: int) -> date:
    return date(year, month, day)


def _price_on_or_after(series: pd.Series, target: date) -> tuple[date, float]:
    if series.empty:
        raise ValueError("No price history available")

    index = pd.to_datetime(series.index).tz_localize(None)
    target_ts = pd.Timestamp(target)
    matches = index[index >= target_ts]
    if matches.empty:
        prior = index[index <= target_ts]
        if prior.empty:
            raise ValueError(f"No price available on or after {target.isoformat()}")
        actual_ts = prior[-1]
    else:
        actual_ts = matches[0]

    value = float(series.loc[actual_ts])
    return actual_ts.date(), value


def _annual_return(buy_price: float, sell_price: float) -> float:
    if buy_price == 0:
        raise ValueError("Buy price cannot be zero")
    return (sell_price / buy_price) - 1.0


def _score_company(ticker: str, valuation_data: dict[str, object], financial_data: dict[str, object]) -> Company:
    company = HistoricalValuationAdapter().adapt(ticker, valuation_data)
    quality_company = HistoricalQualityAdapter().adapt(ticker, financial_data)

    for field, value in quality_company.metrics.__dict__.items():
        if value is not None:
            setattr(company.metrics, field, value)

    calculate_score(company)
    return company


def score_universe_for_year(
    formation_year: int,
    tickers: list[str],
    valuation_repo: CompaniesMarketCapHistoricalValuationRepository | None = None,
    financial_repo: CompaniesMarketCapHistoricalFinancialRepository | None = None,
) -> list[Company]:
    valuation_repo = valuation_repo or CompaniesMarketCapHistoricalValuationRepository()
    financial_repo = financial_repo or CompaniesMarketCapHistoricalFinancialRepository()

    companies: list[Company] = []
    for ticker in tickers:
        try:
            valuation_data = valuation_repo.load(ticker, formation_year)
            financial_data = financial_repo.load(ticker, formation_year)
        except (FileNotFoundError, ValueError):
            continue

        companies.append(_score_company(ticker, valuation_data, financial_data))

    return companies


def rank_companies(companies: list[Company], top_n: int) -> list[Company]:
    def _score_value(company: Company, mode: str) -> float:
        if mode == "quality":
            return company.quality.score
        if mode == "valuation":
            return company.valuation.score
        return overall_score(company)

    ranked = sorted(
        companies,
        key=lambda company: (
            -_score_value(company, "qv"),
            -company.quality.score,
            -company.valuation.score,
            company.ticker,
        ),
    )
    return ranked[:top_n]


def rank_companies_with_mode(companies: list[Company], top_n: int, scoring_mode: str) -> list[Company]:
    mode = scoring_mode.lower().strip()
    if mode not in {"qv", "quality", "valuation"}:
        raise ValueError(f"Unsupported scoring_mode: {scoring_mode}")

    def _primary(company: Company) -> float:
        if mode == "quality":
            return company.quality.score
        if mode == "valuation":
            return company.valuation.score
        return overall_score(company)

    ranked = sorted(
        companies,
        key=lambda company: (
            -_primary(company),
            -company.quality.score,
            -company.valuation.score,
            company.ticker,
        ),
    )
    return ranked[:top_n]


def build_audit_row(
    *,
    formation_year: int,
    rank: int,
    company: Company,
    buy_date: date,
    buy_price: float,
    sell_date: date,
    sell_price: float,
) -> dict[str, object]:
    annual_return = _annual_return(buy_price, sell_price)
    return {
        "formation_year": formation_year,
        "rank": rank,
        "ticker": company.ticker,
        "overall_score": round(overall_score(company), 4),
        "valuation_score": round(company.valuation.score, 4),
        "quality_score": round(company.quality.score, 4),
        "quality_coverage": round(company.quality.coverage, 4),
        "missing_metrics": ", ".join(company.quality.missing_metrics) if company.quality.missing_metrics else "",
        "historical_pe_observations_used": company.valuation_facts.used_pe_count or 0,
        "valuation_percentile": (
            round(company.valuation_facts.historical_percentile, 4)
            if company.valuation_facts.historical_percentile is not None
            else ""
        ),
        "buy_date": buy_date.isoformat(),
        "buy_price": round(buy_price, 4),
        "sell_date": sell_date.isoformat(),
        "sell_price": round(sell_price, 4),
        "annual_return": round(annual_return, 4),
    }


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _summarize_returns(year_results: list[AnnualBacktestYearResult]) -> AnnualBacktestSummary:
    def _max_drawdown(returns: list[float]) -> float:
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for yearly_return in returns:
            equity *= 1.0 + yearly_return
            if equity > peak:
                peak = equity
            drawdown = (equity / peak) - 1.0
            if drawdown < max_dd:
                max_dd = drawdown
        return max_dd

    def _sharpe(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        series = pd.Series(returns, dtype=float)
        std = float(series.std(ddof=1))
        if std == 0:
            return 0.0
        return float(series.mean() / std)

    def _turnover_from_holdings(holdings: list[set[str]], top_n: int) -> float:
        if len(holdings) < 2 or top_n <= 0:
            return 0.0
        turnovers: list[float] = []
        for previous, current in zip(holdings[:-1], holdings[1:]):
            sold = len(previous - current)
            turnovers.append(sold / top_n)
        return sum(turnovers) / len(turnovers) if turnovers else 0.0

    if not year_results:
        return AnnualBacktestSummary(
            years=0,
            portfolio_cagr=0.0,
            benchmark_cagr=0.0,
            excess_cagr=0.0,
            win_rate=0.0,
            cumulative_portfolio_return=0.0,
            cumulative_benchmark_return=0.0,
            portfolio_sharpe=0.0,
            benchmark_sharpe=0.0,
            portfolio_max_drawdown=0.0,
            benchmark_max_drawdown=0.0,
            turnover=0.0,
        )

    portfolio_growth = 1.0
    benchmark_growth = 1.0
    wins = 0
    portfolio_returns = [result.portfolio_return for result in year_results]
    benchmark_returns = [result.benchmark_return for result in year_results]

    for result in year_results:
        portfolio_growth *= 1.0 + result.portfolio_return
        benchmark_growth *= 1.0 + result.benchmark_return
        if result.portfolio_return > result.benchmark_return:
            wins += 1

    years = len(year_results)
    cumulative_portfolio_return = portfolio_growth - 1.0
    cumulative_benchmark_return = benchmark_growth - 1.0

    portfolio_cagr = portfolio_growth ** (1.0 / years) - 1.0 if years else 0.0
    benchmark_cagr = benchmark_growth ** (1.0 / years) - 1.0 if years else 0.0

    return AnnualBacktestSummary(
        years=years,
        portfolio_cagr=portfolio_cagr,
        benchmark_cagr=benchmark_cagr,
        excess_cagr=portfolio_cagr - benchmark_cagr,
        win_rate=wins / years if years else 0.0,
        cumulative_portfolio_return=cumulative_portfolio_return,
        cumulative_benchmark_return=cumulative_benchmark_return,
        portfolio_sharpe=_sharpe(portfolio_returns),
        benchmark_sharpe=_sharpe(benchmark_returns),
        portfolio_max_drawdown=_max_drawdown(portfolio_returns),
        benchmark_max_drawdown=_max_drawdown(benchmark_returns),
        turnover=0.0,
    )


def run_annual_backtest(
    config: AnnualBacktestConfig,
    price_provider: AdjustedCloseProvider | None = None,
) -> AnnualBacktestRunResult:
    price_provider = price_provider or YahooAdjustedCloseProvider()
    universe = load_universe(config.universe_path)
    output_dir = config.output_dir or DEFAULT_OUTPUT_DIR

    buy_targets = [formation_date(year, config.formation_month, config.formation_day) for year in range(config.start_year, config.end_year + 1)]
    sell_targets = [formation_date(year + 1, config.formation_month, config.formation_day) for year in range(config.start_year, config.end_year + 1)]
    coverage_start = min(buy_targets)
    coverage_end = max(sell_targets) + timedelta(days=15)

    benchmark_series = price_provider(config.benchmark_ticker, coverage_start, coverage_end)
    price_cache = {
        ticker: price_provider(ticker, coverage_start, coverage_end)
        for ticker in universe
    }

    audit_rows: list[dict[str, object]] = []
    year_rows: list[dict[str, object]] = []
    year_results: list[AnnualBacktestYearResult] = []
    holdings_by_year: list[set[str]] = []

    for formation_year in range(config.start_year, config.end_year + 1):
        buy_target = formation_date(formation_year, config.formation_month, config.formation_day)
        sell_target = formation_date(formation_year + 1, config.formation_month, config.formation_day)

        companies = score_universe_for_year(formation_year, universe)
        for company in companies:
            company.quality = analyse_quality(company, excluded_metrics=config.quality_metric_exclusions)
        ranked = rank_companies_with_mode(companies, config.top_n, config.scoring_mode)
        holdings_by_year.append({company.ticker for company in ranked})

        try:
            benchmark_buy_date, benchmark_buy_price = _price_on_or_after(benchmark_series, buy_target)
            benchmark_sell_date, benchmark_sell_price = _price_on_or_after(benchmark_series, sell_target)
            benchmark_return = _annual_return(benchmark_buy_price, benchmark_sell_price)
        except ValueError:
            benchmark_buy_date = buy_target
            benchmark_sell_date = sell_target
            benchmark_buy_price = 1.0
            benchmark_sell_price = 1.0
            benchmark_return = 0.0

        holding_returns: list[float] = []
        for rank, company in enumerate(ranked, start=1):
            series = price_cache.get(company.ticker, pd.Series(dtype=float))
            if series.empty:
                continue

            buy_date, buy_price = _price_on_or_after(series, buy_target)
            sell_date, sell_price = _price_on_or_after(series, sell_target)
            holding_return = _annual_return(buy_price, sell_price)
            holding_returns.append(holding_return)

            audit_rows.append(
                build_audit_row(
                    formation_year=formation_year,
                    rank=rank,
                    company=company,
                    buy_date=buy_date,
                    buy_price=buy_price,
                    sell_date=sell_date,
                    sell_price=sell_price,
                )
            )

        portfolio_return = sum(holding_returns) / len(holding_returns) if holding_returns else 0.0
        year_result = AnnualBacktestYearResult(
            formation_year=formation_year,
            buy_date=benchmark_buy_date,
            sell_date=benchmark_sell_date,
            portfolio_return=portfolio_return,
            benchmark_return=benchmark_return,
            excess_return=portfolio_return - benchmark_return,
            selected_count=len(holding_returns),
        )
        year_results.append(year_result)
        year_rows.append(
            {
                "formation_year": formation_year,
                "buy_date": benchmark_buy_date.isoformat(),
                "sell_date": benchmark_sell_date.isoformat(),
                "selected_count": len(holding_returns),
                "portfolio_return": round(portfolio_return, 4),
                "benchmark_return": round(benchmark_return, 4),
                "excess_return": round(portfolio_return - benchmark_return, 4),
            }
        )

    summary = _summarize_returns(year_results)
    summary.turnover = _compute_average_turnover(holdings_by_year, config.top_n)

    audit_path = output_dir / "audit.csv"
    returns_path = output_dir / "returns.csv"

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
        year_rows,
        [
            "formation_year",
            "buy_date",
            "sell_date",
            "selected_count",
            "portfolio_return",
            "benchmark_return",
            "excess_return",
        ],
    )

    return AnnualBacktestRunResult(
        audit_path=audit_path,
        returns_path=returns_path,
        audit_rows=audit_rows,
        year_results=year_results,
        summary=summary,
    )


def _compute_average_turnover(holdings_by_year: list[set[str]], top_n: int) -> float:
    if len(holdings_by_year) < 2 or top_n <= 0:
        return 0.0

    turnovers: list[float] = []
    for previous, current in zip(holdings_by_year[:-1], holdings_by_year[1:]):
        sold = len(previous - current)
        turnovers.append(sold / top_n)
    return sum(turnovers) / len(turnovers) if turnovers else 0.0


def build_experiment_comparison_row(config: AnnualBacktestConfig, result: AnnualBacktestRunResult) -> ExperimentComparisonRow:
    return ExperimentComparisonRow(
        experiment=config.experiment_name,
        scoring_mode=config.scoring_mode,
        formation_month=config.formation_month,
        formation_day=config.formation_day,
        top_n=config.top_n,
        years=result.summary.years,
        cagr=result.summary.portfolio_cagr,
        sharpe=result.summary.portfolio_sharpe,
        max_drawdown=result.summary.portfolio_max_drawdown,
        turnover=result.summary.turnover,
        win_rate_vs_spy=result.summary.win_rate,
        spy_cagr=result.summary.benchmark_cagr,
        excess_cagr=result.summary.excess_cagr,
    )


def run_experiment_suite(
    configs: list[AnnualBacktestConfig],
    output_dir: Path,
    price_provider: AdjustedCloseProvider | None = None,
) -> ExperimentSuiteResult:
    price_provider = price_provider or YahooAdjustedCloseProvider()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[ExperimentComparisonRow] = []
    run_results: dict[str, AnnualBacktestRunResult] = {}

    for config in configs:
        experiment_dir_name = config.experiment_name.lower().replace(" ", "_").replace("/", "_")
        experiment_output_dir = output_dir / experiment_dir_name
        run_result = run_annual_backtest(
            AnnualBacktestConfig(
                start_year=config.start_year,
                end_year=config.end_year,
                formation_month=config.formation_month,
                formation_day=config.formation_day,
                top_n=config.top_n,
                universe_path=config.universe_path,
                output_dir=experiment_output_dir,
                benchmark_ticker=config.benchmark_ticker,
                scoring_mode=config.scoring_mode,
                experiment_name=config.experiment_name,
                quality_metric_exclusions=config.quality_metric_exclusions,
            ),
            price_provider=price_provider,
        )
        run_results[config.experiment_name] = run_result
        rows.append(build_experiment_comparison_row(config, run_result))

    comparison_path = output_dir / "experiment_comparison.csv"
    comparison_rows = [
        {
            "experiment": row.experiment,
            "scoring_mode": row.scoring_mode,
            "formation_month": row.formation_month,
            "formation_day": row.formation_day,
            "top_n": row.top_n,
            "years": row.years,
            "cagr": round(row.cagr, 4),
            "sharpe": round(row.sharpe, 4),
            "max_drawdown": round(row.max_drawdown, 4),
            "turnover": round(row.turnover, 4),
            "win_rate_vs_spy": round(row.win_rate_vs_spy, 4),
            "spy_cagr": round(row.spy_cagr, 4),
            "excess_cagr": round(row.excess_cagr, 4),
        }
        for row in rows
    ]
    _write_csv(
        comparison_path,
        comparison_rows,
        [
            "experiment",
            "scoring_mode",
            "formation_month",
            "formation_day",
            "top_n",
            "years",
            "cagr",
            "sharpe",
            "max_drawdown",
            "turnover",
            "win_rate_vs_spy",
            "spy_cagr",
            "excess_cagr",
        ],
    )

    return ExperimentSuiteResult(rows=rows, comparison_path=comparison_path, run_results=run_results)


def _quality_baseline_config(
    start_year: int,
    end_year: int,
    top_n: int,
    formation_month: int = 4,
    formation_day: int = 1,
) -> AnnualBacktestConfig:
    return AnnualBacktestConfig(
        start_year=start_year,
        end_year=end_year,
        formation_month=formation_month,
        formation_day=formation_day,
        top_n=top_n,
        scoring_mode="quality",
        experiment_name="Q baseline",
    )


def _quality_battle_test_configs(
    start_year: int,
    end_year: int,
    top_n: int,
) -> list[AnnualBacktestConfig]:
    configs: list[AnnualBacktestConfig] = []

    # Baseline
    configs.append(_quality_baseline_config(start_year, end_year, top_n, 4, 1))

    # Different time windows (one dimension changed at a time)
    windows = [
        (2015, 2018, "Q window 2015-2018"),
        (2019, 2022, "Q window 2019-2022"),
        (2023, 2025, "Q window 2023-2025"),
    ]
    for window_start, window_end, name in windows:
        if window_start < start_year or window_end > end_year:
            continue
        configs.append(
            AnnualBacktestConfig(
                start_year=window_start,
                end_year=window_end,
                formation_month=4,
                formation_day=1,
                top_n=top_n,
                scoring_mode="quality",
                experiment_name=name,
            )
        )

    # Different rebalance months
    for month in [1, 4, 7, 10]:
        configs.append(
            AnnualBacktestConfig(
                start_year=start_year,
                end_year=end_year,
                formation_month=month,
                formation_day=1,
                top_n=top_n,
                scoring_mode="quality",
                experiment_name=f"Q rebalance month {month:02d}",
            )
        )

    # Different portfolio sizes
    for n_value in [5, 10, 15, 20]:
        configs.append(
            AnnualBacktestConfig(
                start_year=start_year,
                end_year=end_year,
                formation_month=4,
                formation_day=1,
                top_n=n_value,
                scoring_mode="quality",
                experiment_name=f"Q top {n_value}",
            )
        )

    # Deduplicate by experiment name while preserving order
    deduped: list[AnnualBacktestConfig] = []
    seen: set[str] = set()
    for config in configs:
        if config.experiment_name in seen:
            continue
        seen.add(config.experiment_name)
        deduped.append(config)
    return deduped


def run_leave_one_year_out_quality(
    *,
    start_year: int,
    end_year: int,
    top_n: int,
    output_dir: Path,
    price_provider: AdjustedCloseProvider | None = None,
) -> tuple[list[LeaveOneYearOutRow], Path]:
    price_provider = price_provider or YahooAdjustedCloseProvider()
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = run_annual_backtest(
        _quality_baseline_config(start_year=start_year, end_year=end_year, top_n=top_n, formation_month=4, formation_day=1),
        price_provider=price_provider,
    )

    rows: list[LeaveOneYearOutRow] = []
    full_years = [result.formation_year for result in baseline.year_results]
    for omitted_year in full_years:
        filtered_results = [result for result in baseline.year_results if result.formation_year != omitted_year]
        filtered_summary = _summarize_returns(filtered_results)
        rows.append(
            LeaveOneYearOutRow(
                omitted_year=omitted_year,
                years=filtered_summary.years,
                cagr=filtered_summary.portfolio_cagr,
                sharpe=filtered_summary.portfolio_sharpe,
                max_drawdown=filtered_summary.portfolio_max_drawdown,
                turnover=baseline.summary.turnover,
                win_rate_vs_spy=filtered_summary.win_rate,
                spy_cagr=filtered_summary.benchmark_cagr,
                excess_cagr=filtered_summary.excess_cagr,
            )
        )

    leave_one_out_path = output_dir / "quality_leave_one_year_out.csv"
    _write_csv(
        leave_one_out_path,
        [
            {
                "omitted_year": row.omitted_year,
                "years": row.years,
                "cagr": round(row.cagr, 4),
                "sharpe": round(row.sharpe, 4),
                "max_drawdown": round(row.max_drawdown, 4),
                "turnover": round(row.turnover, 4),
                "win_rate_vs_spy": round(row.win_rate_vs_spy, 4),
                "spy_cagr": round(row.spy_cagr, 4),
                "excess_cagr": round(row.excess_cagr, 4),
            }
            for row in rows
        ],
        [
            "omitted_year",
            "years",
            "cagr",
            "sharpe",
            "max_drawdown",
            "turnover",
            "win_rate_vs_spy",
            "spy_cagr",
            "excess_cagr",
        ],
    )
    return rows, leave_one_out_path


def run_quality_battle_test_suite(
    *,
    start_year: int,
    end_year: int,
    top_n: int,
    output_dir: Path,
    price_provider: AdjustedCloseProvider | None = None,
) -> QualityBattleTestResult:
    price_provider = price_provider or YahooAdjustedCloseProvider()
    output_dir.mkdir(parents=True, exist_ok=True)

    configs = _quality_battle_test_configs(start_year=start_year, end_year=end_year, top_n=top_n)
    experiment_suite = run_experiment_suite(configs=configs, output_dir=output_dir / "quality_one_factor", price_provider=price_provider)
    leave_rows, leave_path = run_leave_one_year_out_quality(
        start_year=start_year,
        end_year=end_year,
        top_n=top_n,
        output_dir=output_dir,
        price_provider=price_provider,
    )

    return QualityBattleTestResult(
        experiment_suite=experiment_suite,
        leave_one_year_out_path=leave_path,
        leave_one_year_out_rows=leave_rows,
    )