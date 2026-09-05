from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quantlab.strategies.qvm.analysis.overall import overall_score
from quantlab.strategies.qvm.analysis.quality import (
    quality_metric_contributions,
    quality_metric_values,
)
from quantlab.strategies.qvm.backtest.annual import score_universe_for_year
from quantlab.strategies.qvm.backtest.common import (
    YahooAdjustedCloseProvider,
    _annual_return,
    _price_on_or_after,
    formation_date,
    load_universe,
)
from quantlab.strategies.qvm.market.models import MarketFacts
from quantlab.strategies.qvm.market.signals import compute_signals


@dataclass(slots=True)
class WinnerRow:
    ticker: str
    buy_date: date
    sell_date: date
    buy_price: float
    sell_price: float
    period_return: float


def _period_return(close: pd.Series, days: int) -> float | None:
    if len(close) < days + 1:
        return None
    start = float(close.iloc[-(days + 1)])
    end = float(close.iloc[-1])
    if start == 0:
        return None
    return (end - start) / start


def _sma(close: pd.Series, window: int) -> float | None:
    if len(close) < window:
        return None
    return float(close.tail(window).mean())


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff().dropna()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.tail(period).mean()
    avg_loss = losses.tail(period).mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _market_facts_as_of(stock_close: pd.Series, spy_close: pd.Series, as_of: date) -> MarketFacts:
    facts = MarketFacts()

    stock_hist = stock_close[stock_close.index <= pd.Timestamp(as_of)]
    spy_hist = spy_close[spy_close.index <= pd.Timestamp(as_of)]
    if stock_hist.empty:
        return facts

    facts.price_history_days = len(stock_hist)
    facts.current_price = float(stock_hist.iloc[-1])

    tail_52w = stock_hist.tail(252)
    if not tail_52w.empty:
        facts.price_52w_high = float(tail_52w.max())
        facts.price_52w_low = float(tail_52w.min())

    facts.return_1m = _period_return(stock_hist, 21)
    facts.return_3m = _period_return(stock_hist, 63)
    facts.return_6m = _period_return(stock_hist, 126)
    facts.return_12m = _period_return(stock_hist, 252)

    if not spy_hist.empty:
        facts.spy_return_6m = _period_return(spy_hist, 126)
        facts.spy_return_12m = _period_return(spy_hist, 252)
        if facts.return_6m is not None and facts.spy_return_6m is not None:
            facts.rs_6m = facts.return_6m - facts.spy_return_6m
        if facts.return_12m is not None and facts.spy_return_12m is not None:
            facts.rs_12m = facts.return_12m - facts.spy_return_12m

    facts.sma_50 = _sma(stock_hist, 50)
    facts.sma_200 = _sma(stock_hist, 200)

    if facts.price_52w_high and facts.price_52w_high > 0:
        facts.distance_from_52w_high_pct = (facts.current_price - facts.price_52w_high) / facts.price_52w_high
    if facts.sma_200 and facts.sma_200 > 0:
        facts.distance_from_sma_200_pct = (facts.current_price - facts.sma_200) / facts.sma_200

    facts.rsi_14 = _rsi(stock_hist, 14)
    return facts


def _safe_round(value: float | None, digits: int = 4) -> float | str:
    if value is None:
        return ""
    return round(value, digits)


def _compute_top_winners(
    *,
    tickers: list[str],
    price_provider: YahooAdjustedCloseProvider,
    coverage_start: date,
    coverage_end: date,
    period_start: date,
    period_end: date,
    top_n: int,
) -> tuple[list[WinnerRow], dict[str, pd.Series]]:
    winners: list[WinnerRow] = []
    price_cache: dict[str, pd.Series] = {}

    for ticker in tickers:
        series = price_provider(ticker, coverage_start, coverage_end)
        price_cache[ticker] = series
        if series.empty:
            continue

        try:
            buy_date, buy_price = _price_on_or_after(series, period_start)
            sell_date, sell_price = _price_on_or_after(series, period_end)
        except ValueError:
            continue

        winners.append(
            WinnerRow(
                ticker=ticker,
                buy_date=buy_date,
                sell_date=sell_date,
                buy_price=float(buy_price),
                sell_price=float(sell_price),
                period_return=_annual_return(float(buy_price), float(sell_price)),
            )
        )

    winners.sort(key=lambda row: row.period_return, reverse=True)
    return winners[:top_n], price_cache


def run_analysis(
    *,
    start_year: int,
    end_year: int,
    formation_month: int,
    formation_day: int,
    top_n: int,
    output_dir: Path,
) -> tuple[Path, Path]:
    universe = load_universe()
    price_provider = YahooAdjustedCloseProvider()

    period_start = formation_date(start_year, formation_month, formation_day)
    period_end = formation_date(end_year + 1, formation_month, formation_day)
    coverage_start = period_start - timedelta(days=800)
    coverage_end = period_end + timedelta(days=15)

    top_winners, price_cache = _compute_top_winners(
        tickers=universe,
        price_provider=price_provider,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        period_start=period_start,
        period_end=period_end,
        top_n=top_n,
    )

    top_tickers = [row.ticker for row in top_winners]
    spy_series = price_provider("SPY", coverage_start, coverage_end)

    summary_rows = [
        {
            "rank": rank,
            "ticker": row.ticker,
            "period_buy_date": row.buy_date.isoformat(),
            "period_buy_price": round(row.buy_price, 4),
            "period_sell_date": row.sell_date.isoformat(),
            "period_sell_price": round(row.sell_price, 4),
            "period_return": round(row.period_return, 6),
        }
        for rank, row in enumerate(top_winners, start=1)
    ]

    yearly_rows: list[dict[str, object]] = []
    for year in range(start_year, end_year + 1):
        buy_target = formation_date(year, formation_month, formation_day)
        sell_target = formation_date(year + 1, formation_month, formation_day)

        intrinsic_price_lookup: dict[str, float | None] = {}
        for ticker in top_tickers:
            series = price_cache.get(ticker, pd.Series(dtype=float))
            if series.empty:
                intrinsic_price_lookup[ticker] = None
                continue
            try:
                _, px = _price_on_or_after(series, buy_target)
                intrinsic_price_lookup[ticker] = float(px)
            except ValueError:
                intrinsic_price_lookup[ticker] = None

        companies = score_universe_for_year(
            year,
            top_tickers,
            intrinsic_price_lookup=intrinsic_price_lookup,
        )
        company_by_ticker = {company.ticker: company for company in companies}

        for ticker in top_tickers:
            series = price_cache.get(ticker, pd.Series(dtype=float))
            if series.empty:
                continue

            try:
                buy_date, buy_price = _price_on_or_after(series, buy_target)
                sell_date, sell_price = _price_on_or_after(series, sell_target)
            except ValueError:
                continue

            facts = _market_facts_as_of(series, spy_series, buy_date)
            signals = compute_signals(facts)

            company = company_by_ticker.get(ticker)
            if company is None:
                yearly_rows.append(
                    {
                        "formation_year": year,
                        "ticker": ticker,
                        "has_fundamental_snapshot": False,
                        "buy_date": buy_date.isoformat(),
                        "buy_price": round(float(buy_price), 4),
                        "sell_date": sell_date.isoformat(),
                        "sell_price": round(float(sell_price), 4),
                        "annual_return": round(_annual_return(float(buy_price), float(sell_price)), 6),
                        "momentum_assessment": signals.assessment,
                        "momentum_trend": signals.trend,
                        "momentum_relative_strength": signals.relative_strength,
                        "momentum_pullback": signals.pullback,
                    }
                )
                continue

            quality_values = quality_metric_values(company)
            quality_contributions = quality_metric_contributions(company)

            row: dict[str, object] = {
                "formation_year": year,
                "ticker": ticker,
                "has_fundamental_snapshot": True,
                "buy_date": buy_date.isoformat(),
                "buy_price": round(float(buy_price), 4),
                "sell_date": sell_date.isoformat(),
                "sell_price": round(float(sell_price), 4),
                "annual_return": round(_annual_return(float(buy_price), float(sell_price)), 6),
                "overall_score": round(overall_score(company), 4),
                "quality_score": round(company.quality.score, 4),
                "quality_coverage": round(company.quality.coverage, 4),
                "quality_missing_metrics": ", ".join(company.quality.missing_metrics) if company.quality.missing_metrics else "",
                "valuation_score": round(company.valuation.score, 4),
                "valuation_band": company.valuation.valuation_band or "",
                "valuation_percentile": _safe_round(company.valuation_facts.historical_percentile, 4),
                "intrinsic_assessment": company.reverse_dcf.assessment,
                "intrinsic_expectation_gap": _safe_round(company.reverse_dcf.expectation_gap, 6),
                "intrinsic_implied_growth": _safe_round(company.reverse_dcf.implied_growth, 6),
                "intrinsic_historical_growth": _safe_round(company.reverse_dcf.historical_growth_estimate, 6),
                "intrinsic_history_quality": company.reverse_dcf.history_quality,
                "intrinsic_growth_input_count": company.reverse_dcf.growth_input_count,
                "momentum_assessment": signals.assessment,
                "momentum_trend": signals.trend,
                "momentum_relative_strength": signals.relative_strength,
                "momentum_pullback": signals.pullback,
                "momentum_return_6m": _safe_round(facts.return_6m, 6),
                "momentum_return_12m": _safe_round(facts.return_12m, 6),
                "momentum_rs_6m": _safe_round(facts.rs_6m, 6),
                "momentum_rs_12m": _safe_round(facts.rs_12m, 6),
                "momentum_rsi_14": _safe_round(facts.rsi_14, 2),
                "momentum_distance_52w_high": _safe_round(facts.distance_from_52w_high_pct, 6),
                "momentum_distance_sma200": _safe_round(facts.distance_from_sma_200_pct, 6),
            }

            for metric_name, value in quality_values.items():
                row[f"quality_metric_{metric_name}"] = _safe_round(value, 6)
            for metric_name, value in quality_contributions.items():
                row[f"quality_contribution_{metric_name}"] = round(value, 4)

            yearly_rows.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    top_winners_path = output_dir / "top_20_price_winners_summary.csv"
    yearly_panel_path = output_dir / "top_20_price_winners_yearly_panel.csv"

    pd.DataFrame(summary_rows).to_csv(top_winners_path, index=False)
    pd.DataFrame(yearly_rows).sort_values(["ticker", "formation_year"]).to_csv(yearly_panel_path, index=False)

    return top_winners_path, yearly_panel_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate top period price winners in the QVM universe and export yearly "
            "quality/valuation/intrinsic/momentum evolution."
        )
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--formation-month", type=int, default=4)
    parser.add_argument("--formation-day", type=int, default=1)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/qvm/backtest/top_winners_evolution"),
    )
    args = parser.parse_args()

    top_winners_path, yearly_panel_path = run_analysis(
        start_year=args.start_year,
        end_year=args.end_year,
        formation_month=args.formation_month,
        formation_day=args.formation_day,
        top_n=args.top_n,
        output_dir=args.output_dir,
    )

    print(f"Top winners summary CSV: {top_winners_path}")
    print(f"Yearly evolution panel CSV: {yearly_panel_path}")


if __name__ == "__main__":
    main()
