from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol
import csv

import pandas as pd
import yfinance as yf

from ..analysis.overall import overall_score
from ..analysis.quality import analyse_quality, quality_eligible
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
    selection_policy: str = "score"
    experiment_name: str = "QV (baseline)"
    quality_metric_exclusions: tuple[str, ...] = ()
    quality_pool_size: int = 20
    valuation_guard_min_score: float = 20.0
    quality_hysteresis_keep_top_n: int = 15
    quality_hysteresis_min_gap: float = 2.0


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
    selection_policy: str
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
    selection_diagnostics_path: Path
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


def _passes_valuation_guard(company: Company, min_valuation_score: float) -> bool:
    return company.valuation.score >= min_valuation_score


def _score_for_mode(company: Company, scoring_mode: str) -> float:
    mode = scoring_mode.lower().strip()
    if mode == "quality":
        return company.quality.score
    if mode == "valuation":
        return company.valuation.score
    return overall_score(company)


def select_companies(
    companies: list[Company],
    *,
    top_n: int,
    scoring_mode: str,
    selection_policy: str,
    quality_pool_size: int,
    valuation_guard_min_score: float,
) -> list[Company]:
    policy = selection_policy.lower().strip()
    if policy == "score":
        return rank_companies_with_mode(companies, top_n, scoring_mode)

    if policy == "quality_soft_valuation_guard":
        ranked_by_quality = rank_companies_with_mode(companies, len(companies), "quality")
        top_quality_pool = ranked_by_quality[:quality_pool_size]
        selected: list[Company] = [
            company
            for company in top_quality_pool
            if _passes_valuation_guard(company, valuation_guard_min_score)
        ]
        if len(selected) >= top_n:
            return selected[:top_n]

        remaining = [
            company
            for company in ranked_by_quality[quality_pool_size:]
            if _passes_valuation_guard(company, valuation_guard_min_score)
        ]
        return (selected + remaining)[:top_n]

    if policy == "quality_cheapest_half":
        ranked_by_quality = rank_companies_with_mode(companies, len(companies), "quality")
        top_quality_pool = ranked_by_quality[:quality_pool_size]
        ranked_by_valuation = sorted(
            top_quality_pool,
            key=lambda company: (
                -company.valuation.score,
                -company.quality.score,
                company.ticker,
            ),
        )
        return ranked_by_valuation[:top_n]

    if policy == "quality_hysteresis":
        return select_companies_quality_hysteresis(
            companies,
            previous_holdings=set(),
            top_n=top_n,
            scoring_mode=scoring_mode,
            keep_top_n=15,
            min_gap=2.0,
        )

    if policy in {"portfolio_signal", "signal_buy_hold", "buy_hold_signal"}:
        return select_companies_portfolio_signal(
            companies,
            top_n=top_n,
            scoring_mode=scoring_mode,
            allowed_actions=("Buy", "Hold", "Accumulate"),
        )

    if policy == "action_simplified_strict_band":
        return select_companies_action_simplified(
            companies,
            top_n=top_n,
            scoring_mode=scoring_mode,
            min_overall_score=80.0,
            allowed_valuation_bands=("Deep Value", "Cheap", "Fair Value"),
        )

    if policy == "action_simplified_relaxed_band":
        return select_companies_action_simplified(
            companies,
            top_n=top_n,
            scoring_mode=scoring_mode,
            min_overall_score=80.0,
            excluded_valuation_bands=("Very Expensive",),
        )

    if policy == "action_simplified_relaxed_score_band":
        return select_companies_action_simplified(
            companies,
            top_n=top_n,
            scoring_mode=scoring_mode,
            min_overall_score=75.0,
            excluded_valuation_bands=("Very Expensive",),
        )

    raise ValueError(f"Unsupported selection_policy: {selection_policy}")


def select_companies_portfolio_signal(
    companies: list[Company],
    *,
    top_n: int,
    scoring_mode: str,
    allowed_actions: tuple[str, ...] = ("Buy", "Hold", "Accumulate"),
) -> list[Company]:
    """Filter companies to the actionable portfolio decisions and rank the survivors.

    This is a separate logic branch from annual rebalance ranking. It intentionally
    uses the portfolio action layer output rather than recomputing an annual score-only
    ranking from the full eligible universe.
    """
    if top_n <= 0:
        return []

    action_set = {action.strip().lower() for action in allowed_actions}
    eligible = [
        company
        for company in companies
        if (company.portfolio.action or "").strip().lower() in action_set
    ]
    if not eligible:
        return []

    return rank_companies_with_mode(eligible, min(top_n, len(eligible)), scoring_mode)[:top_n]


def select_companies_action_simplified(
    companies: list[Company],
    *,
    top_n: int,
    scoring_mode: str,
    min_overall_score: float,
    allowed_valuation_bands: tuple[str, ...] | None = None,
    excluded_valuation_bands: tuple[str, ...] = (),
) -> list[Company]:
    """Simplified action gate for backtests: score threshold + valuation band filter.

    This intentionally avoids market-assessment gates to increase candidate coverage
    while keeping valuation discipline in place.
    """
    if top_n <= 0:
        return []

    allowed_set = set(allowed_valuation_bands or ())
    excluded_set = set(excluded_valuation_bands)

    def _passes_band(company: Company) -> bool:
        band = company.valuation.valuation_band or ""
        if allowed_set and band not in allowed_set:
            return False
        if excluded_set and band in excluded_set:
            return False
        return True

    filtered = [
        company
        for company in companies
        if overall_score(company) >= min_overall_score and _passes_band(company)
    ]
    if not filtered:
        return []

    return rank_companies_with_mode(filtered, min(top_n, len(filtered)), scoring_mode)[:top_n]


def select_companies_quality_hysteresis(
    companies: list[Company],
    previous_holdings: set[str] | None,
    *,
    top_n: int,
    scoring_mode: str,
    keep_top_n: int = 15,
    min_gap: float = 2.0,
) -> list[Company]:
    """Hold a protected band and replace only when a new name is materially better.

    This function intentionally separates the turnover-aware policy from the original
    rank-only strategy so both can be backtested side-by-side.
    """
    if top_n <= 0:
        return []

    ranked = rank_companies_with_mode(companies, len(companies), scoring_mode)
    previous = previous_holdings or set()

    if not previous:
        return ranked[:top_n]

    protected_rank_cutoff = max(top_n, keep_top_n)
    protected = {company.ticker for company in ranked[:protected_rank_cutoff]}
    selected_by_ticker: dict[str, Company] = {}

    # 1. Keep previous holdings as long as they remain in the protected band.
    for company in ranked:
        if company.ticker in previous and company.ticker in protected:
            selected_by_ticker[company.ticker] = company
        if len(selected_by_ticker) >= top_n:
            break

    # 2. Fill remaining slots from the highest-ranked candidates, but only if they are
    # meaningfully stronger than the worst currently-held name.
    for company in ranked:
        if company.ticker in selected_by_ticker:
            continue
        if len(selected_by_ticker) < top_n:
            selected_by_ticker[company.ticker] = company
            continue

        weakest_ticker = min(
            selected_by_ticker,
            key=lambda ticker: _score_for_mode(selected_by_ticker[ticker], scoring_mode),
        )
        candidate_score = _score_for_mode(company, scoring_mode)
        weakest_score = _score_for_mode(selected_by_ticker[weakest_ticker], scoring_mode)

        if candidate_score >= weakest_score + min_gap:
            del selected_by_ticker[weakest_ticker]
            selected_by_ticker[company.ticker] = company

    # Keep deterministic selection order aligned with the ranking list.
    return [company for company in ranked if company.ticker in selected_by_ticker][:top_n]


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


def _safe_quantile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    return float(pd.Series(values, dtype=float).quantile(quantile))


def _band_share(companies: list[Company], allowed_bands: set[str]) -> float:
    if not companies:
        return 0.0
    count = sum(1 for company in companies if (company.valuation.valuation_band or "") in allowed_bands)
    return count / len(companies)


def build_selection_diagnostics_row(
    *,
    formation_year: int,
    eligible_companies: list[Company],
    selected_companies: list[Company],
) -> dict[str, object]:
    universe_val = [company.valuation.score for company in eligible_companies]
    selected_val = [company.valuation.score for company in selected_companies]
    universe_quality = [company.quality.score for company in eligible_companies]
    selected_quality = [company.quality.score for company in selected_companies]
    universe_coverage = [company.quality.coverage for company in eligible_companies]
    selected_coverage = [company.quality.coverage for company in selected_companies]

    universe_val_median = _safe_quantile(universe_val, 0.5)
    selected_val_median = _safe_quantile(selected_val, 0.5)
    selected_val_median_pct_in_universe = (
        float((pd.Series(universe_val, dtype=float) <= selected_val_median).mean()) if universe_val and selected_val else 0.0
    )

    expensive_bands = {"Expensive", "Very Expensive"}
    cheap_bands = {"Deep Value", "Cheap"}

    universe_expensive_share = _band_share(eligible_companies, expensive_bands)
    selected_expensive_share = _band_share(selected_companies, expensive_bands)
    universe_cheap_share = _band_share(eligible_companies, cheap_bands)
    selected_cheap_share = _band_share(selected_companies, cheap_bands)

    universe_quality_median = _safe_quantile(universe_quality, 0.5)
    selected_quality_median = _safe_quantile(selected_quality, 0.5)
    universe_coverage_median = _safe_quantile(universe_coverage, 0.5)
    selected_coverage_median = _safe_quantile(selected_coverage, 0.5)

    return {
        "formation_year": formation_year,
        "universe_n": len(eligible_companies),
        "selected_n": len(selected_companies),
        "universe_val_median": round(universe_val_median, 4),
        "selected_val_median": round(selected_val_median, 4),
        "val_median_spread": round(selected_val_median - universe_val_median, 4),
        "selected_val_median_pct_in_universe": round(selected_val_median_pct_in_universe, 4),
        "universe_expensive_share": round(universe_expensive_share, 4),
        "selected_expensive_share": round(selected_expensive_share, 4),
        "expensive_share_spread": round(selected_expensive_share - universe_expensive_share, 4),
        "universe_cheap_share": round(universe_cheap_share, 4),
        "selected_cheap_share": round(selected_cheap_share, 4),
        "cheap_share_spread": round(selected_cheap_share - universe_cheap_share, 4),
        "universe_quality_median": round(universe_quality_median, 4),
        "selected_quality_median": round(selected_quality_median, 4),
        "quality_median_spread": round(selected_quality_median - universe_quality_median, 4),
        "universe_coverage_median": round(universe_coverage_median, 4),
        "selected_coverage_median": round(selected_coverage_median, 4),
        "coverage_median_spread": round(selected_coverage_median - universe_coverage_median, 4),
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
    selection_diagnostics_rows: list[dict[str, object]] = []
    year_rows: list[dict[str, object]] = []
    year_results: list[AnnualBacktestYearResult] = []
    holdings_by_year: list[set[str]] = []

    for formation_year in range(config.start_year, config.end_year + 1):
        buy_target = formation_date(formation_year, config.formation_month, config.formation_day)
        sell_target = formation_date(formation_year + 1, config.formation_month, config.formation_day)

        companies = score_universe_for_year(formation_year, universe)
        for company in companies:
            company.quality = analyse_quality(company, excluded_metrics=config.quality_metric_exclusions)
        eligible_companies = [c for c in companies if quality_eligible(c)]

        previous_holdings = holdings_by_year[-1] if holdings_by_year else set()
        if config.selection_policy.lower().strip() == "quality_hysteresis":
            ranked = select_companies_quality_hysteresis(
                eligible_companies,
                previous_holdings,
                top_n=config.top_n,
                scoring_mode=config.scoring_mode,
                keep_top_n=config.quality_hysteresis_keep_top_n,
                min_gap=config.quality_hysteresis_min_gap,
            )
        else:
            ranked = select_companies(
                eligible_companies,
                top_n=config.top_n,
                scoring_mode=config.scoring_mode,
                selection_policy=config.selection_policy,
                quality_pool_size=config.quality_pool_size,
                valuation_guard_min_score=config.valuation_guard_min_score,
            )
        holdings_by_year.append({company.ticker for company in ranked})
        selection_diagnostics_rows.append(
            build_selection_diagnostics_row(
                formation_year=formation_year,
                eligible_companies=eligible_companies,
                selected_companies=ranked,
            )
        )

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

    return AnnualBacktestRunResult(
        audit_path=audit_path,
        returns_path=returns_path,
        selection_diagnostics_path=selection_diagnostics_path,
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
        selection_policy=config.selection_policy,
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
                selection_policy=config.selection_policy,
                experiment_name=config.experiment_name,
                quality_metric_exclusions=config.quality_metric_exclusions,
                quality_pool_size=config.quality_pool_size,
                valuation_guard_min_score=config.valuation_guard_min_score,
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
            "selection_policy": row.selection_policy,
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
            "selection_policy",
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