from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import Provider
from ..models import Company


class CompaniesMarketCapProvider(Provider):

    REPO_ROOT = Path(__file__).resolve().parents[5]
    DATA_DIR = REPO_ROOT / "data" / "qvm" / "companiesmarketcap"
    SUMMARY_PATH = DATA_DIR / "companiesmarketcap_summary.csv"

    def load(self, ticker: str) -> Company:
        ticker = ticker.upper()

        summary_row = self._load_summary_row(ticker)
        name = summary_row.get("name")
        slug = summary_row["slug"]

        company = Company(
            ticker=ticker,
            name=name,
        )

        valuation_facts = self._load_valuation_facts(ticker, slug)
        if valuation_facts is not None:
            company.valuation_facts.historical_pe_values = valuation_facts["historical_pe_values"]
            company.valuation_facts.historical_average_pe = valuation_facts["historical_average_pe"]
            company.valuation_facts.historical_median_pe = valuation_facts["historical_median_pe"]
            company.valuation_facts.historical_percentile = valuation_facts["historical_percentile"]
            company.valuation_facts.current_pe = valuation_facts["current_pe"]
            company.valuation_facts.requested_historical_years = valuation_facts["requested_historical_years"]
            company.valuation_facts.valid_pe_count = valuation_facts["valid_pe_count"]
            company.valuation_facts.outliers_removed = valuation_facts["outliers_removed"]
            company.valuation_facts.used_pe_count = valuation_facts["used_pe_count"]

        return company

    def _load_summary_row(self, ticker: str) -> dict[str, str]:
        if not self.SUMMARY_PATH.exists():
            raise FileNotFoundError(
                f"CompaniesMarketCap summary file not found: {self.SUMMARY_PATH}"
            )

        summary_df = pd.read_csv(self.SUMMARY_PATH, dtype=str)
        matching = summary_df[summary_df["ticker"].str.upper() == ticker]
        if matching.empty:
            raise ValueError(f"No CompaniesMarketCap summary entry for ticker: {ticker}")

        row = matching.iloc[0]
        return {
            "ticker": row["ticker"],
            "name": row.get("name", None),
            "slug": row["slug"],
        }

    def _load_valuation_facts(self, ticker: str, slug: str) -> dict[str, object] | None:
        valuation_path = self._find_valuation_path(ticker, slug)
        if valuation_path is None or not valuation_path.exists():
            raise FileNotFoundError(
                f"CompaniesMarketCap valuation CSV not found for {ticker}: {slug}"
            )

        df = pd.read_csv(valuation_path)
        expected_columns = {"Year", "pe_ratio"}
        if not expected_columns.issubset(set(df.columns)):
            raise ValueError(
                f"Expected columns {expected_columns} in {valuation_path}, got {list(df.columns)}"
            )

        requested_years = 15

        df = df.copy()
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
        df["pe_ratio"] = pd.to_numeric(df["pe_ratio"], errors="coerce")
        df = df.dropna(subset=["Year", "pe_ratio"])
        if df.empty:
            return None

        df = df[df["pe_ratio"] > 0]
        if df.empty:
            return None

        valid_pe_count = len(df)
        q1 = df["pe_ratio"].quantile(0.25)
        q3 = df["pe_ratio"].quantile(0.75)
        iqr = q3 - q1
        outliers_removed = 0
        if iqr > 0:
            max_allowed = q3 + 3 * iqr
            df_filtered = df[df["pe_ratio"] <= max_allowed]
            if len(df_filtered) >= 5:
                outliers_removed = valid_pe_count - len(df_filtered)
                df = df_filtered

        df = df.sort_values("Year", ascending=False).drop_duplicates(subset=["Year"]).head(requested_years)
        df = df.sort_values("Year")

        pe_values = df["pe_ratio"].tolist()
        if not pe_values:
            return None

        current_pe = float(pe_values[-1])
        historical_pe_values = [float(value) for value in pe_values]
        historical_average_pe = float(pd.Series(pe_values).mean())
        historical_median_pe = float(pd.Series(pe_values).median())
        historical_percentile = self._percentile(historical_pe_values, current_pe)

        return {
            "historical_pe_values": historical_pe_values,
            "historical_average_pe": historical_average_pe,
            "historical_median_pe": historical_median_pe,
            "historical_percentile": historical_percentile,
            "current_pe": current_pe,
            "requested_historical_years": requested_years,
            "valid_pe_count": valid_pe_count,
            "outliers_removed": outliers_removed,
            "used_pe_count": len(pe_values),
        }

    def _find_valuation_path(self, ticker: str, slug: str) -> Path | None:
        candidates = []

        exact = self.DATA_DIR / f"{ticker.lower()}_{slug}_valuation.csv"
        if exact.exists():
            return exact

        candidates.extend(self.DATA_DIR.glob(f"{ticker.lower()}_*_valuation.csv"))
        candidates.extend(self.DATA_DIR.glob(f"{slug}_valuation.csv"))
        candidates.extend(self.DATA_DIR.glob(f"{ticker.lower()}_valuation.csv"))
        candidates.extend(self.DATA_DIR.glob(f"*{slug}*_valuation.csv"))
        candidates.extend(self.DATA_DIR.glob(f"*{ticker.lower()}*_valuation.csv"))

        for candidate in candidates:
            name = candidate.name.lower()
            if slug in name or ticker.lower() in name:
                return candidate

        fallback = list(self.DATA_DIR.glob("*_valuation.csv"))
        return fallback[0] if fallback else None

    def _percentile(self, values: list[float], current_value: float) -> float | None:
        if not values:
            return None

        sorted_values = sorted(values)
        count = len(sorted_values)
        rank = sum(1 for value in sorted_values if value <= current_value)
        return float((rank - 1) / max(count - 1, 1))
