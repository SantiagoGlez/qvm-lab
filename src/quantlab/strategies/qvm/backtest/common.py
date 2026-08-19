from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Protocol
import csv

import pandas as pd
import yfinance as yf

from ..ticker_aliases import YAHOO_TICKER_MAP


REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_UNIVERSE_PATH = REPO_ROOT / "data" / "qvm" / "companies.csv"
DEFAULT_ANNUAL_OUTPUT_DIR = REPO_ROOT / "data" / "qvm" / "backtest" / "annual_portfolio"
DEFAULT_CONTRIBUTION_OUTPUT_DIR = REPO_ROOT / "data" / "qvm" / "backtest" / "contribution_portfolio"


class AdjustedCloseProvider(Protocol):
    def __call__(self, ticker: str, start: date, end: date) -> pd.Series:
        raise NotImplementedError


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


def add_months(value: date, months: int) -> date:
    return (pd.Timestamp(value) + pd.DateOffset(months=months)).date()


def iter_contribution_dates(start: date, end: date, contribution_months: int) -> list[date]:
    if contribution_months <= 0:
        raise ValueError("contribution_months must be positive")

    dates: list[date] = []
    current = start
    while current < end:
        dates.append(current)
        current = add_months(current, contribution_months)
    return dates


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


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def xirr(cash_flows: list[tuple[date, float]]) -> float:
    if len(cash_flows) < 2:
        return 0.0

    ordered = sorted(cash_flows, key=lambda item: item[0])
    base_date = ordered[0][0]

    def npv(rate: float) -> float:
        if rate <= -1.0:
            return float("inf")
        total = 0.0
        for cash_date, amount in ordered:
            years = (cash_date - base_date).days / 365.25
            total += amount / ((1.0 + rate) ** years)
        return total

    low = -0.9999
    high = 10.0
    low_value = npv(low)
    high_value = npv(high)

    for _ in range(40):
        if low_value == 0:
            return low
        if high_value == 0:
            return high
        if low_value * high_value < 0:
            break
        high *= 2.0
        high_value = npv(high)
    else:
        return 0.0

    for _ in range(100):
        mid = (low + high) / 2.0
        mid_value = npv(mid)
        if abs(mid_value) < 1e-9:
            return mid
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    return (low + high) / 2.0