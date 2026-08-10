import logging
import pandas as pd
import yfinance as yf
from pathlib import Path

from .base import Provider
from ..models import Company
from ..ticker_aliases import YAHOO_TICKER_MAP

_log = logging.getLogger(__name__)


class YahooProvider(Provider):

    def load(self, ticker: str) -> Company:

        yf_ticker = YAHOO_TICKER_MAP.get(ticker, ticker)
        stock = yf.Ticker(yf_ticker)

        info = stock.info

        company = Company(
            ticker=ticker,
            name=info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
        )

        company.metrics.forward_pe = info.get("forwardPE")
        company.metrics.trailing_pe = info.get("trailingPE")

        company.metrics.market_cap = info.get("marketCap")

        company.metrics.roe = info.get("returnOnEquity")
        company.metrics.roic = self._calculate_roic(stock)
        company.metrics.gross_margin = info.get("grossMargins")
        company.metrics.operating_margin = info.get("operatingMargins")
        revenue_cagr, revenue_cagr_years = self._calculate_cagr(stock, "Total Revenue")
        eps_cagr, eps_cagr_years = self._calculate_cagr(stock, "Diluted EPS", fallback="Basic EPS")
        company.metrics.revenue_cagr = revenue_cagr
        company.metrics.eps_cagr = eps_cagr
        company.metrics.revenue_cagr_years = revenue_cagr_years
        company.metrics.eps_cagr_years = eps_cagr_years
        fcf_margin, fcf_conversion = self._calculate_fcf_metrics(stock)
        company.metrics.fcf_margin = fcf_margin
        company.metrics.fcf_conversion = fcf_conversion
        net_cash, net_debt_ebitda, interest_coverage, debt_to_ebitda = self._calculate_financial_health(stock)
        company.metrics.net_cash = net_cash
        company.metrics.net_debt_ebitda = net_debt_ebitda
        company.metrics.interest_coverage = interest_coverage
        company.metrics.debt_to_ebitda = debt_to_ebitda

        live_pe = self._calculate_live_pe(info)
        if live_pe is not None:
            company.valuation_facts.current_pe = live_pe
            company.valuation_facts.current_pe_source = "Yahoo (Price / TTM EPS)"

        historical_pe = self._historical_pe(stock, ticker)
        if historical_pe:
            company.valuation_facts.historical_pe_values = historical_pe
            company.valuation_facts.historical_average_pe = float(pd.Series(historical_pe).mean())
            company.valuation_facts.historical_median_pe = float(pd.Series(historical_pe).median())
            company.valuation_facts.historical_percentile = self._percentile(historical_pe, historical_pe[-1])

        return company

    def _calculate_live_pe(self, info: dict) -> float | None:
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        trailing_eps = info.get("trailingEps")
        if price is not None and trailing_eps is not None and float(trailing_eps) > 0:
            return float(price) / float(trailing_eps)
        return None

    def _calculate_financial_health(self, stock: yf.Ticker) -> tuple[float | None, float | None, float | None, float | None]:
        """Returns (net_cash, net_debt_ebitda, interest_coverage, debt_to_ebitda)."""
        ticker = getattr(stock, "ticker", "?")
        try:
            inc = stock.income_stmt
            bal = stock.balance_sheet
            if inc is None or inc.empty or bal is None or bal.empty:
                return None, None, None, None

            inc_col = inc.columns[0]
            bal_col = bal.columns[0]

            # --- Net Cash (positive = cash, negative = debt) ---
            net_cash = None
            if "Net Debt" in bal.index and not pd.isna(bal.loc["Net Debt", bal_col]):
                net_cash = -float(bal.loc["Net Debt", bal_col])  # Net Debt convention is debt minus cash
            elif "Total Debt" in bal.index and "Cash Cash Equivalents And Short Term Investments" in bal.index:
                net_cash = float(bal.loc["Cash Cash Equivalents And Short Term Investments", bal_col]) - float(bal.loc["Total Debt", bal_col])

            # --- EBITDA for normalization ---
            ebitda = None
            for label in ("EBITDA", "Normalized EBITDA"):
                if label in inc.index and not pd.isna(inc.loc[label, inc_col]):
                    ebitda = float(inc.loc[label, inc_col])
                    break

            # --- Net Debt / EBITDA (negative = net cash = good) ---
            net_debt_ebitda = None
            if net_cash is not None and ebitda and ebitda != 0:
                net_debt_ebitda = -net_cash / ebitda  # convert net_cash sign back to net_debt

            # --- Interest Coverage (EBIT / |Interest Expense|) ---
            interest_coverage = None
            ebit = None
            for label in ("EBIT", "Operating Income"):
                if label in inc.index and not pd.isna(inc.loc[label, inc_col]):
                    ebit = float(inc.loc[label, inc_col])
                    break
            interest_expense = None
            for label in ("Interest Expense Non Operating", "Interest Expense"):
                if label in inc.index and not pd.isna(inc.loc[label, inc_col]):
                    val = float(inc.loc[label, inc_col])
                    if val != 0:
                        interest_expense = abs(val)
                        break
            if ebit is not None and interest_expense:
                interest_coverage = ebit / interest_expense

            # --- Debt / EBITDA (fallback) ---
            debt_to_ebitda = None
            if "Total Debt" in bal.index and ebitda and ebitda > 0:
                debt_to_ebitda = float(bal.loc["Total Debt", bal_col]) / ebitda

            return net_cash, net_debt_ebitda, interest_coverage, debt_to_ebitda
        except Exception as exc:
            _log.warning("[HEALTH] %s: unexpected error — %s", ticker, exc)
            return None, None, None, None

    def _calculate_fcf_metrics(self, stock: yf.Ticker) -> tuple[float | None, float | None]:
        ticker = getattr(stock, "ticker", "?")
        try:
            cf = stock.cash_flow
            inc = stock.income_stmt
            if cf is None or cf.empty or inc is None or inc.empty:
                return None, None

            col = cf.columns[0]

            fcf = None
            for label in ("Free Cash Flow", "Operating Cash Flow"):
                if label in cf.index and not pd.isna(cf.loc[label, col]):
                    if label == "Operating Cash Flow" and "Capital Expenditure" in cf.index:
                        capex = cf.loc["Capital Expenditure", col]
                        fcf = float(cf.loc[label, col]) + float(capex)  # capex is negative
                    else:
                        fcf = float(cf.loc[label, col])
                    break

            if fcf is None:
                _log.debug("[FCF] %s: could not resolve FCF", ticker)
                return None, None

            inc_col = inc.columns[0]
            revenue, net_income = None, None
            for label in ("Total Revenue", "Operating Revenue"):
                if label in inc.index and not pd.isna(inc.loc[label, inc_col]):
                    revenue = float(inc.loc[label, inc_col])
                    break
            for label in ("Net Income", "Net Income Common Stockholders"):
                if label in inc.index and not pd.isna(inc.loc[label, inc_col]):
                    net_income = float(inc.loc[label, inc_col])
                    break

            fcf_margin = fcf / revenue if revenue and revenue != 0 else None
            fcf_conversion = fcf / net_income if net_income and net_income != 0 else None

            return fcf_margin, fcf_conversion
        except Exception as exc:
            _log.warning("[FCF] %s: unexpected error — %s", ticker, exc)
            return None, None

    def _calculate_cagr(self, stock: yf.Ticker, label: str, fallback: str | None = None) -> tuple[float | None, int | None]:
        ticker = getattr(stock, "ticker", "?")
        try:
            inc = stock.income_stmt
            if inc is None or inc.empty:
                return None, None

            row = None
            if label in inc.index:
                row = inc.loc[label].dropna()
            elif fallback and fallback in inc.index:
                row = inc.loc[fallback].dropna()

            if row is None or len(row) < 2:
                _log.debug("[CAGR] %s: insufficient data for '%s'", ticker, label)
                return None, None

            row = row.sort_index(ascending=False)  # most recent first
            end_val = float(row.iloc[0])

            if end_val <= 0:
                _log.debug("[CAGR] %s: most recent value for '%s' is non-positive", ticker, label)
                return None, None

            # Traverse from oldest to newest; use first strictly positive value as start
            start_val, n = None, None
            for i in range(len(row) - 1, 0, -1):
                candidate = float(row.iloc[i])
                if candidate > 0:
                    start_val = candidate
                    n = i  # years between row[i] (oldest) and row[0] (newest)
                    break

            if start_val is None:
                _log.debug("[CAGR] %s: no positive start value found for '%s'", ticker, label)
                return None, None

            # Require at least 3 annual observations (n >= 2 intervals)
            if n < 2:
                _log.debug("[CAGR] %s: only %d year(s) of valid data for '%s', need at least 2", ticker, n, label)
                return None, None

            return (end_val / start_val) ** (1.0 / n) - 1.0, n
        except Exception as exc:
            _log.warning("[CAGR] %s: unexpected error for '%s' — %s", ticker, label, exc)
            return None, None

    def _calculate_roic(self, stock: yf.Ticker) -> float | None:
        ticker = getattr(stock, "ticker", "?")
        try:
            inc = stock.income_stmt
            bal = stock.balance_sheet
            if inc is None or inc.empty or bal is None or bal.empty:
                _log.debug("[ROIC] %s: income_stmt or balance_sheet unavailable", ticker)
                return None

            col = inc.columns[0]

            # --- EBIT: primary label then fallbacks ---
            ebit = None
            for label in ("EBIT", "Operating Income", "Total Operating Income As Reported"):
                if label in inc.index and not pd.isna(inc.loc[label, col]):
                    ebit = float(inc.loc[label, col])
                    break

            # --- Tax rate: explicit rate, else derive from provision / pretax ---
            tax_rate = None
            if "Tax Rate For Calcs" in inc.index and not pd.isna(inc.loc["Tax Rate For Calcs", col]):
                tax_rate = float(inc.loc["Tax Rate For Calcs", col])
            else:
                provision_labels = ("Tax Provision", "Income Tax Expense", "Tax Expense")
                pretax_labels = ("Pretax Income", "Income Before Tax", "Earnings Before Tax")
                provision, pretax = None, None
                for label in provision_labels:
                    if label in inc.index and not pd.isna(inc.loc[label, col]):
                        provision = float(inc.loc[label, col])
                        break
                for label in pretax_labels:
                    if label in inc.index and not pd.isna(inc.loc[label, col]):
                        pretax = float(inc.loc[label, col])
                        break
                if provision is not None and pretax and pretax != 0:
                    tax_rate = provision / pretax

            # --- Invested Capital: primary label then fallbacks ---
            invested_capital = None
            for label in ("Invested Capital", "Total Capitalization", "Total Equity Gross Minority Interest"):
                if label in bal.index and not pd.isna(bal.loc[label, col]):
                    invested_capital = float(bal.loc[label, col])
                    break

            if ebit is None:
                _log.debug("[ROIC] %s: could not resolve EBIT", ticker)
                return None
            if tax_rate is None:
                _log.debug("[ROIC] %s: could not resolve tax rate", ticker)
                return None
            if invested_capital is None:
                _log.debug("[ROIC] %s: could not resolve invested capital", ticker)
                return None
            if invested_capital == 0:
                _log.debug("[ROIC] %s: invested capital is zero", ticker)
                return None

            nopat = ebit * (1.0 - tax_rate)
            return nopat / invested_capital
        except Exception as exc:
            _log.warning("[ROIC] %s: unexpected error — %s", ticker, exc)
            return None

    def _historical_pe(self, stock: yf.Ticker, ticker: str, period: str = "10y") -> list[float]:
        prices_df = stock.history(period=period)[["Close"]]
        if prices_df.empty:
            return []

        # Helper to try extracting EPS series from various yfinance endpoints
        def extract_eps_from_df(df) -> pd.Series | None:
            if df is None or df.empty:
                return None

            # Case 1: df is a wide table with metrics in the index and dates as columns
            for label in ["Diluted EPS", "Basic EPS", "EPS", "Earnings"]:
                if label in df.index:
                    row = df.loc[label]
                    s = pd.Series(row.values, index=pd.to_datetime(row.index))
                    s = s.dropna()
                    if not s.empty:
                        return s.sort_index()

            # Case 2: df is long table with Date/EPS columns
            if "Date" in df.columns and ("EPS" in df.columns or "Earnings" in df.columns):
                col = "EPS" if "EPS" in df.columns else "Earnings"
                s = pd.Series(df[col].values, index=pd.to_datetime(df["Date"]))
                s = s.dropna()
                if not s.empty:
                    return s.sort_index()

            return None

        # Try quarterly first, then annual, then other earnings tables
        eps_series = None
        try:
            eps_series = extract_eps_from_df(getattr(stock, "quarterly_financials", pd.DataFrame()))
        except Exception:
            eps_series = None

        if eps_series is None:
            try:
                eps_series = extract_eps_from_df(getattr(stock, "financials", pd.DataFrame()))
            except Exception:
                eps_series = None

        if eps_series is None:
            try:
                eps_series = extract_eps_from_df(getattr(stock, "quarterly_earnings", pd.DataFrame()))
            except Exception:
                eps_series = None

        if eps_series is None:
            try:
                eps_series = extract_eps_from_df(getattr(stock, "earnings", pd.DataFrame()))
            except Exception:
                eps_series = None

        if eps_series is None or eps_series.empty:
            return []

        # Detect periodicity using median difference in months
        months = eps_series.index.to_series().diff().dropna().dt.days.abs().median() / 30.0
        if months <= 4.5:
            window = 4  # quarterly
        elif 4.5 < months <= 8.5:
            window = 2  # semi-annual
        else:
            window = 1  # annual or sparse

        # Rolling TTM EPS (sum of last `window` periods)
        ttm_eps = eps_series.rolling(window=window).sum().dropna()

        # If TTM series is too short, fall back to annual EPS series
        if window > 1 and len(ttm_eps) < 8:
            ann = extract_eps_from_df(getattr(stock, "financials", pd.DataFrame()))
            if ann is not None and not ann.empty:
                ttm_eps = ann.sort_index()

        if ttm_eps.empty:
            return []

        eps_df = pd.DataFrame({"Date": ttm_eps.index, "EPS": ttm_eps.values})
        eps_df["Date"] = pd.to_datetime(eps_df["Date"]).dt.tz_localize(None)
        eps_df = eps_df.sort_values("Date")

        prices_df = prices_df.copy()
        prices_df.index = prices_df.index.tz_localize(None)
        prices_df = prices_df.reset_index()
        prices_df.columns = ["Date", "Close"]

        merged = pd.merge_asof(prices_df.sort_values("Date"), eps_df, on="Date", direction="backward")
        merged = merged.dropna(subset=["Close", "EPS"])

        if merged.empty:
            return []

        merged["PE_Ratio"] = merged["Close"] / merged["EPS"]

        # persist merged series for inspection / reproducibility
        try:
            cache_dir = Path("data/cache")
            cache_dir.mkdir(parents=True, exist_ok=True)
            out_file = cache_dir / f"{ticker}_pe.csv"
            merged.to_csv(out_file, index=False)
        except Exception:
            pass

        return [float(value) for value in merged["PE_Ratio"].tolist()]

    def _percentile(self, values: list[float], current_value: float) -> float | None:
        if not values:
            return None

        series = pd.Series(values)
        if series.empty:
            return None

        return float(series.rank(method="average", pct=True).iloc[-1])