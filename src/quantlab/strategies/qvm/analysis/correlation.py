from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from ..backtest.common import AdjustedCloseProvider, YahooAdjustedCloseProvider


@dataclass(slots=True)
class CorrelationAsset:
    ticker: str
    group: str
    label: str | None = None
    weight: float | None = None

    @property
    def column_name(self) -> str:
        return f"{self.group}:{self.ticker.upper()}"

    @property
    def display_name(self) -> str:
        if self.label and self.label.strip():
            return self.label.strip()
        return self.ticker.upper()


@dataclass(slots=True)
class CorrelationAnalysisResult:
    assets: list[CorrelationAsset]
    portfolio_assets: list[CorrelationAsset]
    reference_assets: list[CorrelationAsset]
    price_frame: pd.DataFrame
    return_frame: pd.DataFrame
    portfolio_returns: pd.Series
    correlation_matrix: pd.DataFrame
    summary_table: pd.DataFrame
    missing_assets: list[str]


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_asset_csv(path: Path, group: str) -> list[CorrelationAsset]:
    frame = pd.read_csv(path, dtype=str)
    if "ticker" not in frame.columns:
        raise ValueError(f"Asset file must contain a 'ticker' column: {path}")

    assets: list[CorrelationAsset] = []
    for row in frame.to_dict(orient="records"):
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        label = str(row.get("label", "")).strip() or None
        weight = _coerce_optional_float(row.get("weight"))
        assets.append(CorrelationAsset(ticker=ticker, group=group, label=label, weight=weight))
    return assets


def load_correlation_assets(
    portfolio_path: Path,
    reference_path: Path | None = None,
) -> tuple[list[CorrelationAsset], list[CorrelationAsset], list[CorrelationAsset]]:
    portfolio_assets = _read_asset_csv(portfolio_path, group="portfolio")
    reference_assets: list[CorrelationAsset] = []
    if reference_path is not None:
        reference_assets = _read_asset_csv(reference_path, group="reference")
    assets = [*portfolio_assets, *reference_assets]
    if not assets:
        raise ValueError("No assets were loaded for correlation analysis")
    if not portfolio_assets:
        raise ValueError(f"Portfolio file contains no tickers: {portfolio_path}")
    return assets, portfolio_assets, reference_assets


def _normalized_weights(assets: list[CorrelationAsset]) -> pd.Series:
    if not assets:
        raise ValueError("At least one portfolio asset is required")

    weights = pd.Series(
        [asset.weight if asset.weight is not None else 1.0 for asset in assets],
        index=[asset.column_name for asset in assets],
        dtype=float,
    )
    total = float(weights.sum())
    if total <= 0:
        weights[:] = 1.0 / len(weights)
        return weights
    return weights / total


def _build_price_frame(
    assets: list[CorrelationAsset],
    start: date,
    end: date,
    price_provider: AdjustedCloseProvider,
) -> tuple[pd.DataFrame, list[str]]:
    series_map: dict[str, pd.Series] = {}
    missing: list[str] = []

    for asset in assets:
        series = price_provider(asset.ticker, start, end)
        if series.empty:
            missing.append(asset.column_name)
            continue
        clean = series.dropna().sort_index().astype(float)
        if clean.empty:
            missing.append(asset.column_name)
            continue
        clean.index = pd.to_datetime(clean.index).tz_localize(None)
        series_map[asset.column_name] = clean.rename(asset.column_name)

    if not series_map:
        raise ValueError("No price history was available for the selected assets")

    frame = pd.concat(series_map.values(), axis=1).sort_index()
    return frame, missing


def _portfolio_return_series(return_frame: pd.DataFrame, portfolio_assets: list[CorrelationAsset]) -> pd.Series:
    if not portfolio_assets:
        raise ValueError("Portfolio assets are required to calculate portfolio correlation")

    weights = _normalized_weights(portfolio_assets)
    portfolio_columns = [asset.column_name for asset in portfolio_assets if asset.column_name in return_frame.columns]
    if not portfolio_columns:
        raise ValueError("Portfolio return columns are missing from the return frame")

    portfolio_weights = weights.reindex(portfolio_columns)
    portfolio_weights = portfolio_weights / portfolio_weights.sum()

    weighted_rows: list[float] = []
    for _, row in return_frame[portfolio_columns].iterrows():
        valid = row.dropna()
        if valid.empty:
            weighted_rows.append(float("nan"))
            continue
        valid_weights = portfolio_weights.reindex(valid.index).dropna()
        valid_values = valid.reindex(valid_weights.index)
        valid_weight_sum = float(valid_weights.sum())
        if valid_weight_sum <= 0:
            weighted_rows.append(float("nan"))
            continue
        weighted_rows.append(float((valid_values * valid_weights).sum() / valid_weight_sum))

    return pd.Series(weighted_rows, index=return_frame.index, name="portfolio")


def build_correlation_analysis(
    portfolio_path: Path,
    reference_path: Path | None = None,
    start: date | None = None,
    end: date | None = None,
    price_provider: AdjustedCloseProvider | None = None,
) -> CorrelationAnalysisResult:
    today = date.today()
    if start is None:
        start = (pd.Timestamp(today) - pd.DateOffset(years=5)).date()
    if end is None:
        end = today
    if start > end:
        raise ValueError("start must be on or before end")

    assets, portfolio_assets, reference_assets = load_correlation_assets(portfolio_path, reference_path)
    provider = price_provider or YahooAdjustedCloseProvider()
    price_frame, missing_assets = _build_price_frame(assets, start, end, provider)
    return_frame = price_frame.pct_change().dropna(how="all")
    portfolio_returns = _portfolio_return_series(return_frame, portfolio_assets)

    analysis_frame = return_frame.copy()
    analysis_frame[portfolio_returns.name] = portfolio_returns
    correlation_matrix = analysis_frame.corr()

    summary_rows: list[dict[str, object]] = []
    for asset in assets:
        summary_rows.append(
            {
                "group": asset.group,
                "ticker": asset.ticker,
                "label": asset.display_name,
                "column_name": asset.column_name,
                "weight": asset.weight,
                "correlation_with_portfolio": correlation_matrix.loc[portfolio_returns.name, asset.column_name],
                "mean_return": float(return_frame[asset.column_name].mean()),
                "volatility": float(return_frame[asset.column_name].std()),
            }
        )

    summary_table = pd.DataFrame(summary_rows)
    summary_table = summary_table.sort_values(by=["group", "ticker"]).reset_index(drop=True)

    return CorrelationAnalysisResult(
        assets=assets,
        portfolio_assets=portfolio_assets,
        reference_assets=reference_assets,
        price_frame=price_frame,
        return_frame=return_frame,
        portfolio_returns=portfolio_returns,
        correlation_matrix=correlation_matrix,
        summary_table=summary_table,
        missing_assets=missing_assets,
    )


def write_correlation_report(result: CorrelationAnalysisResult, output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = output_dir / "correlation_matrix.csv"
    summary_path = output_dir / "correlation_summary.csv"
    returns_path = output_dir / "portfolio_returns.csv"

    result.correlation_matrix.to_csv(matrix_path)
    result.summary_table.to_csv(summary_path, index=False)
    result.portfolio_returns.rename("portfolio_return").to_frame().to_csv(returns_path)
    return matrix_path, summary_path, returns_path