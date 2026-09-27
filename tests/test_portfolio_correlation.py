from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from quantlab.strategies.qvm.analysis.correlation import build_correlation_analysis, write_correlation_report


class _FakePriceProvider:
    def __init__(self, price_map: dict[str, pd.Series]) -> None:
        self.price_map = price_map

    def __call__(self, ticker: str, start: date, end: date) -> pd.Series:
        return self.price_map[ticker.upper()]


def _price_series(base: float, returns: list[float], dates: pd.DatetimeIndex) -> pd.Series:
    prices = [base]
    for daily_return in returns:
        prices.append(prices[-1] * (1.0 + daily_return))
    return pd.Series(prices, index=dates)


def test_build_correlation_analysis_includes_external_assets_and_portfolio_returns(tmp_path: Path) -> None:
    portfolio_file = tmp_path / "portfolio.csv"
    portfolio_file.write_text("ticker,weight\nAAA,0.6\nBBB,0.4\n", encoding="utf-8")

    reference_file = tmp_path / "reference.csv"
    reference_file.write_text("ticker,label\nGLD,Gold\nTLT,US Bonds\n", encoding="utf-8")

    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    price_map = {
        "AAA": _price_series(100.0, [0.01, 0.02, -0.01, 0.03], dates),
        "BBB": _price_series(100.0, [0.00, 0.01, 0.02, -0.01], dates),
        "GLD": _price_series(100.0, [0.005, 0.00, 0.01, 0.00], dates),
        "TLT": _price_series(100.0, [-0.005, 0.00, -0.01, 0.01], dates),
    }

    result = build_correlation_analysis(
        portfolio_path=portfolio_file,
        reference_path=reference_file,
        start=date(2025, 1, 1),
        end=date(2025, 1, 5),
        price_provider=_FakePriceProvider(price_map),
    )

    expected_portfolio_returns = pd.Series(
        [0.006, 0.016, 0.002, 0.014],
        index=dates[1:],
        name="portfolio",
    )

    pd.testing.assert_series_equal(result.portfolio_returns.round(6), expected_portfolio_returns)
    assert result.missing_assets == []
    assert set(result.summary_table["group"]) == {"portfolio", "reference"}
    assert {"portfolio:AAA", "portfolio:BBB", "reference:GLD", "reference:TLT", "portfolio"}.issubset(
        set(result.correlation_matrix.columns)
    )

    matrix_path, summary_path, returns_path = write_correlation_report(result, tmp_path / "out")
    assert matrix_path.exists()
    assert summary_path.exists()
    assert returns_path.exists()