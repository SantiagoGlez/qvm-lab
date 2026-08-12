from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd

from .temporal import filter_to_formation_year


class HistoricalValuationRepository(ABC):
    """Repository interface for valuation history as of a formation year."""

    @abstractmethod
    def load(self, ticker: str, formation_year: int) -> dict[str, Any]:
        """Return valuation history limited to data available at formation_year."""
        raise NotImplementedError


class HistoricalFinancialRepository(ABC):
    """Repository interface for financial metrics as of a formation year."""

    @abstractmethod
    def load(self, ticker: str, formation_year: int) -> dict[str, Any]:
        """Return financial metrics restricted to information available by formation_year."""
        raise NotImplementedError


class CompaniesMarketCapHistoricalValuationRepository(HistoricalValuationRepository):
    """Historical PE repository backed by the CompaniesMarketCap valuation CSVs."""

    REPO_ROOT = Path(__file__).resolve().parents[5]
    DATA_DIR = REPO_ROOT / "data" / "qvm" / "companiesmarketcap"

    def load(self, ticker: str, formation_year: int) -> dict[str, Any]:
        ticker = ticker.upper()
        path = self._resolve_path(ticker)
        df = pd.read_csv(path)

        filtered = self._filter_years(df, formation_year)
        if filtered.empty:
            raise ValueError(f"No valuation data available for {ticker} as of {formation_year}")

        pe_values = pd.to_numeric(filtered["pe_ratio"], errors="coerce").dropna().tolist()
        if not pe_values:
            raise ValueError(f"No valid PE observations for {ticker} as of {formation_year}")

        pe_series = pd.Series(pe_values)
        current_pe = float(pe_series.iloc[-1])

        return {
            "ticker": ticker,
            "formation_year": formation_year,
            "historical_pe_values": [float(value) for value in pe_values],
            "historical_average_pe": float(pe_series.mean()),
            "historical_median_pe": float(pe_series.median()),
            "historical_percentile": float(self._percentile(pe_values, current_pe)),
            "current_pe": current_pe,
            "used_pe_count": len(pe_values),
        }

    def _resolve_path(self, ticker: str) -> Path:
        matches = list(self.DATA_DIR.glob(f"{ticker.lower()}_*_valuation.csv"))
        if not matches:
            matches = list(self.DATA_DIR.glob(f"*{ticker.lower()}*_valuation.csv"))
        if not matches:
            raise FileNotFoundError(f"No valuation CSV found for ticker {ticker}")
        return matches[0]

    def _filter_years(self, df: pd.DataFrame, formation_year: int) -> pd.DataFrame:
        df = df.copy()
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
        df["pe_ratio"] = pd.to_numeric(df["pe_ratio"], errors="coerce")
        df = df.dropna(subset=["Year", "pe_ratio"]).copy()
        df = df[df["pe_ratio"] > 0].copy()
        filtered = filter_to_formation_year(df, formation_year)
        if filtered.empty:
            return filtered
        return filtered.sort_values("Year").reset_index(drop=True)

    def _percentile(self, values: list[float], current_value: float) -> float:
        if not values:
            return 0.0
        rank = sum(1 for value in values if value <= current_value)
        count = len(values)
        return max(0.0, min(1.0, (rank - 1) / max(count - 1, 1)))


class CompaniesMarketCapHistoricalFinancialRepository(HistoricalFinancialRepository):
    """Historical fundamentals repository backed by the CompaniesMarketCap financial CSVs."""

    REPO_ROOT = Path(__file__).resolve().parents[5]
    DATA_DIR = REPO_ROOT / "data" / "qvm" / "companiesmarketcap"

    @staticmethod
    def _as_float(value: object) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    @classmethod
    def _prefer_primary_then_fallback(cls, primary_value: object, fallback_value: object) -> float | None:
        primary = cls._as_float(primary_value)
        if primary is not None:
            return primary
        return cls._as_float(fallback_value)

    def load(self, ticker: str, formation_year: int) -> dict[str, Any]:
        ticker = ticker.upper()
        path = self._resolve_path(ticker)
        df = pd.read_csv(path)

        # For all quality metrics we keep the planned MVP rule: use the most recent
        # financial year before the formation year (Y-1) as the reference snapshot.
        # Growth metrics such as CAGR are then computed from the trailing window that
        # ends at that reference year, not from the future formation year itself.
        reference_year = formation_year - 1
        reference_history = self._reference_history(df, reference_year)
        if reference_history.empty:
            raise ValueError(f"No financial data available for {ticker} as of {formation_year}")

        row = reference_history.iloc[-1]
        year = int(row["Year"])

        revenue_cagr, revenue_cagr_years = self._compute_cagr(reference_history, "revenue", window_years=3)
        eps_cagr, eps_cagr_years = self._compute_cagr(reference_history, "eps", window_years=3)
        share_count_cagr, share_count_cagr_years = self._compute_cagr(reference_history, "shares_outstanding", window_years=3)
        sec_snapshot = self._load_sec_probe_snapshot(ticker, year)

        revenue = self._prefer_primary_then_fallback(row.get("revenue"), sec_snapshot.get("revenue"))
        net_income = self._prefer_primary_then_fallback(row.get("net_income"), sec_snapshot.get("net_income"))
        cash = self._prefer_primary_then_fallback(row.get("cash"), sec_snapshot.get("cash_total"))
        total_debt = self._prefer_primary_then_fallback(row.get("total_debt"), sec_snapshot.get("debt_computed"))
        operating_cash_flow = self._prefer_primary_then_fallback(
            row.get("operating_cash_flow"), sec_snapshot.get("operating_cash_flow")
        )
        capex = self._prefer_primary_then_fallback(row.get("capex"), sec_snapshot.get("capex"))
        ebit = self._prefer_primary_then_fallback(row.get("ebit"), sec_snapshot.get("ebit"))
        tax_provision = self._prefer_primary_then_fallback(row.get("tax_provision"), sec_snapshot.get("tax_provision"))
        pretax_income = self._prefer_primary_then_fallback(row.get("pretax_income"), sec_snapshot.get("pretax_income"))
        free_cash_flow = self._prefer_primary_then_fallback(row.get("free_cash_flow"), sec_snapshot.get("fcf_computed"))

        return {
            "ticker": ticker,
            "formation_year": formation_year,
            "year": year,
            "revenue": revenue,
            "net_income": net_income,
            "eps": float(row["eps"]) if pd.notna(row.get("eps")) else None,
            "operating_margin": self._to_decimal(row.get("operating_margin")),
            "cash": cash,
            "total_debt": total_debt,
            "total_assets": float(row["total_assets"]) if pd.notna(row.get("total_assets")) else None,
            "net_assets": float(row["net_assets"]) if pd.notna(row.get("net_assets")) else None,
            "shares_outstanding": float(row["shares_outstanding"]) if pd.notna(row.get("shares_outstanding")) else None,
            "dividend_yield": self._to_decimal(row.get("dividend_yield")),
            "revenue_cagr": revenue_cagr,
            "revenue_cagr_years": revenue_cagr_years,
            "eps_cagr": eps_cagr,
            "eps_cagr_years": eps_cagr_years,
            "share_count_cagr": share_count_cagr,
            "share_count_cagr_years": share_count_cagr_years,
            "roic": sec_snapshot.get("roic_computed"),
            "operating_cash_flow": operating_cash_flow,
            "capex": capex,
            "free_cash_flow": free_cash_flow,
            "ebit": ebit,
            "tax_provision": tax_provision,
            "pretax_income": pretax_income,
            "effective_tax_rate": sec_snapshot.get("effective_tax_rate"),
            "equity": sec_snapshot.get("equity"),
            "short_term_investments": sec_snapshot.get("short_term_investments"),
        }

    def _load_sec_probe_snapshot(self, ticker: str, year: int) -> dict[str, float | None]:
        sec_probe_path = self.DATA_DIR / f"{ticker.lower()}_sec_companyfacts_probe.csv"
        if not sec_probe_path.exists():
            return {}

        df = pd.read_csv(sec_probe_path)
        if df.empty or "year" not in df.columns:
            return {}

        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        row = df[df["year"] == int(year)]
        if row.empty:
            return {}

        snapshot = row.iloc[-1].to_dict()

        keys = [
            "revenue",
            "net_income",
            "roic_computed",
            "operating_cash_flow",
            "capex",
            "fcf_computed",
            "ebit",
            "tax_provision",
            "pretax_income",
            "effective_tax_rate",
            "cash",
            "cash_total",
            "debt_total",
            "debt_computed",
            "equity",
            "short_term_investments",
        ]

        normalized: dict[str, float | None] = {}
        for key in keys:
            value = snapshot.get(key)
            normalized[key] = float(value) if pd.notna(value) else None

        return normalized

    def _resolve_path(self, ticker: str) -> Path:
        matches = list(self.DATA_DIR.glob(f"{ticker.lower()}_*_financials.csv"))
        if not matches:
            matches = list(self.DATA_DIR.glob(f"*{ticker.lower()}*_financials.csv"))
        if not matches:
            raise FileNotFoundError(f"No financials CSV found for ticker {ticker}")
        return matches[0]

    def _select_yearly_snapshot(self, df: pd.DataFrame, formation_year: int) -> pd.DataFrame:
        df = df.copy()
        if "Year" in df.columns:
            year_col = "Year"
        elif "year" in df.columns:
            year_col = "year"
            df = df.rename(columns={"year": "Year"})
        else:
            raise KeyError("Expected a year column in the financial dataset")

        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
        for column in ["revenue", "net_income", "eps", "operating_margin", "cash", "total_debt", "total_assets", "net_assets", "shares_outstanding", "dividend_yield"]:
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")

        filtered = filter_to_formation_year(df, formation_year)
        if filtered.empty:
            return filtered

        prior_year_snapshot = filtered[filtered["Year"] < formation_year]
        if prior_year_snapshot.empty:
            return filtered.iloc[:0].copy()
        return prior_year_snapshot.sort_values("Year").reset_index(drop=True)

    def _reference_history(self, df: pd.DataFrame, reference_year: int) -> pd.DataFrame:
        return self._select_yearly_snapshot(df, reference_year + 1)

    def _compute_cagr(self, df: pd.DataFrame, column: str, window_years: int = 3) -> tuple[float | None, int | None]:
        if column not in df.columns or df.empty:
            return None, None

        series = df[["Year", column]].dropna().sort_values("Year").copy()
        if len(series) < 2:
            return None, None

        trailing = series.tail(window_years)
        if len(trailing) < 2:
            return None, None

        start_value = float(trailing.iloc[0][column])
        end_value = float(trailing.iloc[-1][column])
        if start_value <= 0 or end_value <= 0:
            return None, None

        periods = len(trailing) - 1
        if periods <= 0:
            return None, None

        return float((end_value / start_value) ** (1.0 / periods) - 1.0), len(trailing)

    def _to_decimal(self, value: object) -> float | None:
        if value is None or pd.isna(value):
            return None

        number = float(value)
        if number is None:
            return None
        if abs(number) > 1.0:
            return number / 100.0
        return number
