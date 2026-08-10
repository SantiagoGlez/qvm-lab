"""Market data service.

Responsibilities
----------------
- Download historical price data from Yahoo Finance.
- Compute raw metrics (returns, moving averages, RSI, volatility).
- No business rules or signal interpretation.

All outputs are stored in MarketFacts.
"""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

from .models import MarketFacts
from ..ticker_aliases import YAHOO_TICKER_MAP

_log = logging.getLogger(__name__)


def fetch_market_facts(ticker: str, period: str = "2y") -> MarketFacts:
    """Download historical prices and compute raw market metrics.

    Parameters
    ----------
    ticker:
        Equity ticker symbol.
    period:
        Lookback window passed to yfinance (default ``"2y"``).
        Must cover at least 252 trading days for 12M return.

    Returns
    -------
    MarketFacts
        Populated with raw metrics; individual fields are ``None`` when
        insufficient data is available.
    """
    facts = MarketFacts()

    yf_ticker = YAHOO_TICKER_MAP.get(ticker, ticker)
    try:
        tickers_data = yf.download([yf_ticker, "SPY"], period=period, auto_adjust=True, progress=False)
    except Exception as exc:
        _log.warning("[MARKET] %s: failed to download history — %s", ticker, exc)
        return facts

    try:
        close_all = tickers_data["Close"]
        close = close_all[yf_ticker].dropna()
        spy_close = close_all["SPY"].dropna()
    except Exception as exc:
        _log.warning("[MARKET] %s: failed to extract price series — %s", ticker, exc)
        return facts

    if close.empty or len(close) < 20:
        _log.debug("[MARKET] %s: insufficient price history (%d rows)", ticker, len(close))
        return facts

    close = close.copy()
    facts.price_history_days = len(close)

    # --- Price levels ---------------------------------------------------------
    facts.current_price = float(close.iloc[-1])
    facts.price_52w_high = float(close.tail(252).max())
    facts.price_52w_low = float(close.tail(252).min())

    # --- Returns --------------------------------------------------------------
    facts.return_1m  = _period_return(close, 21)
    facts.return_3m  = _period_return(close, 63)
    facts.return_6m  = _period_return(close, 126)
    facts.return_12m = _period_return(close, 252)

    # --- Relative strength vs SPY --------------------------------------------
    if not spy_close.empty:
        facts.spy_return_6m  = _period_return(spy_close, 126)
        facts.spy_return_12m = _period_return(spy_close, 252)
        if facts.return_6m is not None and facts.spy_return_6m is not None:
            facts.rs_6m  = facts.return_6m  - facts.spy_return_6m
        if facts.return_12m is not None and facts.spy_return_12m is not None:
            facts.rs_12m = facts.return_12m - facts.spy_return_12m

    # --- Moving averages ------------------------------------------------------
    facts.sma_50  = _sma(close, 50)
    facts.sma_200 = _sma(close, 200)

    # --- Distance metrics -----------------------------------------------------
    if facts.price_52w_high and facts.price_52w_high > 0:
        facts.distance_from_52w_high_pct = (
            (facts.current_price - facts.price_52w_high) / facts.price_52w_high
        )
    if facts.sma_200 and facts.sma_200 > 0:
        facts.distance_from_sma_200_pct = (
            (facts.current_price - facts.sma_200) / facts.sma_200
        )

    # --- RSI(14) --------------------------------------------------------------
    facts.rsi_14 = _rsi(close, 14)

    # --- Volatility (30-day, annualised) --------------------------------------
    facts.volatility_30d = _annualised_volatility(close, 30)

    return facts


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

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


def _annualised_volatility(close: pd.Series, window: int = 30) -> float | None:
    if len(close) < window + 1:
        return None
    daily_returns = close.pct_change().dropna().tail(window)
    if daily_returns.empty:
        return None
    return float(daily_returns.std() * (252 ** 0.5))
