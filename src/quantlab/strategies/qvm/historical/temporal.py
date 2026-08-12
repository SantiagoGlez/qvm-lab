from __future__ import annotations

import pandas as pd


class HistoricalDataCutoffError(ValueError):
    """Raised when historical data includes observations newer than the requested formation year."""


def validate_history_cutoff(df: pd.DataFrame, as_of_year: int) -> None:
    """Raise if the dataset contains any row newer than the formation year."""
    if df.empty:
        return

    if "Year" not in df.columns:
        raise KeyError("Year column is required to enforce historical cutoff rules")

    filtered = df.copy()
    filtered["Year"] = pd.to_numeric(filtered["Year"], errors="coerce")
    filtered = filtered.dropna(subset=["Year"]).copy()

    future_rows = filtered[filtered["Year"] > as_of_year]
    if not future_rows.empty:
        raise HistoricalDataCutoffError(
            f"Historical data contains observations after formation year {as_of_year}: "
            f"years {sorted(future_rows['Year'].unique().tolist())}"
        )


def filter_to_formation_year(df: pd.DataFrame, as_of_year: int) -> pd.DataFrame:
    """Return only rows with Year <= as_of_year.

    This function is intentionally a pure filter: it trims the history to the formation-year
    cutoff. Future-data leakage is validated separately by validate_history_cutoff().
    """
    if df.empty:
        return df.copy()

    if "Year" not in df.columns:
        raise KeyError("Year column is required to enforce historical cutoff rules")

    filtered = df.copy()
    filtered["Year"] = pd.to_numeric(filtered["Year"], errors="coerce")
    filtered = filtered.dropna(subset=["Year"]).copy()

    return filtered[filtered["Year"] <= as_of_year].sort_values("Year").reset_index(drop=True)
