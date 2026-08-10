"""Portfolio service.

Responsibilities
----------------
- Load the portfolio CSV.
- Answer "Do we currently own this company?"

Intentionally minimal — quantities, cost basis and P&L are out of scope.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

_PORTFOLIO_PATH = Path(__file__).resolve().parents[5] / "data" / "qvm" / "portfolio.csv"


@lru_cache(maxsize=1)
def _load_tickers() -> frozenset[str]:
    """Load portfolio tickers from CSV, uppercased for case-insensitive matching."""
    if not _PORTFOLIO_PATH.exists():
        return frozenset()

    df = pd.read_csv(_PORTFOLIO_PATH, dtype=str)
    if "ticker" not in df.columns:
        return frozenset()

    return frozenset(df["ticker"].dropna().str.strip().str.upper())


def owns(ticker: str) -> bool:
    """Return True if the ticker is currently in the portfolio."""
    return ticker.strip().upper() in _load_tickers()
