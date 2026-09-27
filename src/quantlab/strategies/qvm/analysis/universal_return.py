from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite

import yfinance as yf

from ..models import Company


@dataclass(slots=True)
class UniversalReturnInputs:
    ticker: str
    price_current: float | None
    eps_ttm: float | None
    pe_current: float | None
    pe_historical_median: float | None
    dividend_yield: float | None
    buyback_rate: float | None
    roe_ttm: float | None
    retention_rate: float | None
    revenue_cagr_10y: float | None


@dataclass(slots=True)
class UniversalReturnResult:
    ticker: str
    horizon_years: int
    line_1_capital_yield: float | None
    line_2_fundamental_growth: float | None
    line_3_valuation_delta: float | None
    expected_annual_return: float | None
    growth_fundamental_raw: float | None
    pe_current_effective: float | None
    confidence_label: str
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def _is_valid_number(value: float | None) -> bool:
    return value is not None and isfinite(value)


def _clamp(value: float, floor: float, ceil: float) -> float:
    return min(max(value, floor), ceil)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if not _is_valid_number(numerator) or not _is_valid_number(denominator):
        return None
    if denominator == 0:
        return None
    return float(numerator / denominator)


def _normalize_fraction(value: float | None) -> float | None:
    if not _is_valid_number(value):
        return None
    # Yahoo returns dividendYield in percentage points for the data we use here.
    # Convert to decimal fraction for downstream calculations.
    return float(value) / 100.0


def _build_missing_inputs(inputs: UniversalReturnInputs, result: UniversalReturnResult | None = None) -> list[str]:
    missing: list[str] = []
    for field_name in (
        "price_current",
        "eps_ttm",
        "pe_current",
        "pe_historical_median",
        "dividend_yield",
        "buyback_rate",
        "roe_ttm",
        "retention_rate",
        "revenue_cagr_10y",
    ):
        if getattr(inputs, field_name) is None:
            missing.append(field_name)

    if result is not None:
        if result.line_2_fundamental_growth is None and "revenue_cagr_10y" not in missing:
            missing.append("revenue_cagr_10y (fallback unavailable)")
        if result.line_3_valuation_delta is None:
            missing.append("valuation anchor (current PE / historical median PE)")

    return missing


def _humanize_missing_input(name: str) -> str:
    mapping = {
        "price_current": "current price",
        "eps_ttm": "TTM EPS",
        "pe_current": "current PE",
        "pe_historical_median": "historical median PE",
        "dividend_yield": "dividend yield",
        "buyback_rate": "buyback rate",
        "roe_ttm": "ROE TTM",
        "retention_rate": "retention rate",
        "revenue_cagr_10y": "10Y revenue CAGR",
        "revenue_cagr_10y (fallback unavailable)": "10Y revenue CAGR fallback",
        "valuation anchor (current PE / historical median PE)": "valuation anchor (current PE or historical median PE)",
    }
    return mapping.get(name, name.replace("_", " "))


def _confidence_label(missing_inputs: list[str], warnings: list[str], assumptions: list[str]) -> str:
    if warnings:
        return "Low"
    if len(missing_inputs) == 0 and len(assumptions) == 0:
        return "High"
    if len(missing_inputs) <= 1 and len(assumptions) <= 1:
        return "Medium"
    return "Low"


def estimate_buyback_rate(ticker: str, lookback_years: int = 3) -> float | None:
    """Estimate annualized net share count change; positive means buyback."""
    try:
        yf_ticker = yf.Ticker(ticker)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(lookback_years * 365.25))
        shares = yf_ticker.get_shares_full(start=start, end=end)
    except Exception:
        return None

    if shares is None:
        return None

    try:
        clean = shares.dropna()
    except Exception:
        return None

    if len(clean) < 2:
        return None

    first_value = float(clean.iloc[0])
    last_value = float(clean.iloc[-1])
    if first_value <= 0 or last_value <= 0:
        return None

    first_index = clean.index[0].to_pydatetime().replace(tzinfo=timezone.utc)
    last_index = clean.index[-1].to_pydatetime().replace(tzinfo=timezone.utc)
    years = max((last_index - first_index).days / 365.25, 1e-6)

    share_growth = (last_value / first_value) ** (1.0 / years) - 1.0
    buyback_rate = -share_growth
    # Ignore clearly broken share-history series or implausible annual rates.
    if abs(buyback_rate) > 0.20:
        return None
    return buyback_rate


def build_universal_inputs(company: Company) -> UniversalReturnInputs:
    ticker = company.ticker

    price_current = company.market_facts.current_price
    eps_ttm = None
    trailing_pe = company.metrics.trailing_pe
    if _is_valid_number(price_current) and _is_valid_number(trailing_pe) and trailing_pe and trailing_pe > 0:
        eps_ttm = price_current / trailing_pe

    pe_current = company.valuation_facts.current_pe
    if not _is_valid_number(pe_current):
        pe_current = trailing_pe
    if not _is_valid_number(pe_current) and _is_valid_number(price_current) and _is_valid_number(eps_ttm):
        pe_current = _safe_ratio(price_current, eps_ttm)

    pe_historical_median = company.valuation_facts.historical_median_pe

    dividend_yield = None
    payout_ratio = None
    try:
        info = yf.Ticker(ticker).info
        dividend_yield = info.get("dividendYield")
        payout_ratio = info.get("payoutRatio")
    except Exception:
        info = {}

    if dividend_yield is not None:
        try:
            dividend_yield = _normalize_fraction(float(dividend_yield))
        except (TypeError, ValueError):
            dividend_yield = None

    if payout_ratio is not None:
        try:
            payout_ratio = float(payout_ratio)
        except (TypeError, ValueError):
            payout_ratio = None

    retention_rate = None
    if _is_valid_number(payout_ratio):
        retention_rate = 1.0 - float(payout_ratio)
    elif _is_valid_number(dividend_yield) and _is_valid_number(price_current) and _is_valid_number(eps_ttm) and eps_ttm and eps_ttm > 0:
        dividend_per_share = float(dividend_yield) * float(price_current)
        implied_payout = dividend_per_share / float(eps_ttm)
        retention_rate = 1.0 - implied_payout
    else:
        retention_rate = 1.0

    if retention_rate is not None:
        retention_rate = _clamp(retention_rate, -0.5, 1.2)

    buyback_rate = estimate_buyback_rate(ticker)

    return UniversalReturnInputs(
        ticker=ticker,
        price_current=price_current,
        eps_ttm=eps_ttm,
        pe_current=pe_current,
        pe_historical_median=pe_historical_median,
        dividend_yield=dividend_yield,
        buyback_rate=buyback_rate,
        roe_ttm=company.metrics.roe,
        retention_rate=retention_rate,
        revenue_cagr_10y=company.reverse_dcf.revenue_cagr_10y,
    )


def calculate_universal_return(inputs: UniversalReturnInputs, horizon_years: int = 5) -> UniversalReturnResult:
    warnings: list[str] = []
    assumptions: list[str] = []

    dividend_yield = inputs.dividend_yield or 0.0
    buyback_rate = inputs.buyback_rate if _is_valid_number(inputs.buyback_rate) else 0.0

    if inputs.buyback_rate is None:
        assumptions.append("Buyback rate unavailable; set to 0%.")

    yield_capital = dividend_yield + buyback_rate

    if _is_valid_number(inputs.retention_rate) and _is_valid_number(inputs.roe_ttm):
        growth_fundamental = float(inputs.retention_rate) * float(inputs.roe_ttm)
    else:
        growth_fundamental = None

    growth_normalized: float | None
    if growth_fundamental is None:
        growth_normalized = inputs.revenue_cagr_10y
        assumptions.append("Used 10Y revenue CAGR because retention*ROE was unavailable.")
    elif growth_fundamental > 0.25 or growth_fundamental < -0.05:
        growth_normalized = inputs.revenue_cagr_10y
        assumptions.append("Fundamental growth outlier; replaced with 10Y revenue CAGR guardrail.")
    else:
        growth_normalized = _clamp(growth_fundamental, 0.02, 0.15)

    pe_current_effective = inputs.pe_current
    if not _is_valid_number(pe_current_effective) or float(pe_current_effective) <= 0:
        if _is_valid_number(inputs.pe_historical_median) and float(inputs.pe_historical_median) > 0:
            pe_current_effective = inputs.pe_historical_median
            assumptions.append("Current PE unavailable/non-positive; used historical median PE as normalized anchor.")
        else:
            pe_current_effective = None
            warnings.append("Cannot compute valuation re-rating: missing valid current PE and historical median PE.")
    elif float(pe_current_effective) > 50:
        if _is_valid_number(inputs.pe_historical_median) and float(inputs.pe_historical_median) > 0:
            pe_current_effective = inputs.pe_historical_median
            assumptions.append("Current PE above 50; replaced with normalized historical median PE.")
        else:
            warnings.append("Current PE above 50 and no historical median PE fallback; valuation delta may be distorted.")

    multiple_revaluation: float | None = None
    if (
        _is_valid_number(pe_current_effective)
        and _is_valid_number(inputs.pe_historical_median)
        and float(pe_current_effective) > 0
        and float(inputs.pe_historical_median) > 0
    ):
        multiple_revaluation = (float(inputs.pe_historical_median) / float(pe_current_effective)) ** (1.0 / horizon_years) - 1.0

    expected_total_return: float | None = None
    if _is_valid_number(growth_normalized) and _is_valid_number(multiple_revaluation):
        expected_total_return = yield_capital + float(growth_normalized) + float(multiple_revaluation)
    elif _is_valid_number(growth_normalized):
        expected_total_return = yield_capital + float(growth_normalized)
        warnings.append("Valuation delta omitted from expected return due to missing/invalid PE anchors.")
    else:
        warnings.append("Expected return incomplete: growth component unavailable.")

    provisional_result = UniversalReturnResult(
        ticker=inputs.ticker,
        horizon_years=horizon_years,
        line_1_capital_yield=yield_capital,
        line_2_fundamental_growth=growth_normalized,
        line_3_valuation_delta=multiple_revaluation,
        expected_annual_return=expected_total_return,
        growth_fundamental_raw=growth_fundamental,
        pe_current_effective=pe_current_effective,
        confidence_label="",
        missing_inputs=[],
        warnings=warnings,
        assumptions=assumptions,
    )

    missing_inputs = _build_missing_inputs(inputs, provisional_result)
    confidence_label = _confidence_label(missing_inputs, warnings, assumptions)

    provisional_result.confidence_label = confidence_label
    provisional_result.missing_inputs = missing_inputs
    return provisional_result


def _pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100.0:+.2f}%"


def format_universal_return_report(inputs: UniversalReturnInputs, result: UniversalReturnResult) -> str:
    lines: list[str] = []
    lines.append("Universal Shareholder Return (Informative)")
    lines.append("-" * 46)
    lines.append(f"Ticker                 {result.ticker}")
    lines.append(f"Horizon                {result.horizon_years} years")
    lines.append(f"Confidence             {result.confidence_label}")
    lines.append("")
    lines.append("Inputs")
    lines.append(f"  Price (current)       {inputs.price_current if inputs.price_current is not None else 'N/A'}")
    lines.append(f"  EPS TTM (derived)     {inputs.eps_ttm if inputs.eps_ttm is not None else 'N/A'}")
    lines.append(f"  PE current            {inputs.pe_current if inputs.pe_current is not None else 'N/A'}")
    lines.append(f"  PE hist median        {inputs.pe_historical_median if inputs.pe_historical_median is not None else 'N/A'}")
    lines.append(f"  Dividend yield        {_pct(inputs.dividend_yield)}")
    lines.append(f"  Buyback rate          {_pct(inputs.buyback_rate)}")
    lines.append(f"  ROE TTM               {_pct(inputs.roe_ttm)}")
    lines.append(f"  Retention rate        {_pct(inputs.retention_rate)}")
    lines.append(f"  Revenue CAGR 10Y      {_pct(inputs.revenue_cagr_10y)}")
    lines.append("")
    lines.append("Three Lines")
    lines.append(f"  Line 1 Capital Yield  {_pct(result.line_1_capital_yield)}")
    lines.append(f"  Line 2 Fund Growth    {_pct(result.line_2_fundamental_growth)}")
    lines.append(f"  Line 3 Valuation      {_pct(result.line_3_valuation_delta)}")
    lines.append(f"  Expected Annual Ret   {_pct(result.expected_annual_return)}")
    lines.append("")
    lines.append("Diagnostics")
    lines.append(f"  Raw g (ret*roe)       {_pct(result.growth_fundamental_raw)}")
    lines.append(
        "  PE current effective  "
        + (f"{result.pe_current_effective:.2f}" if result.pe_current_effective is not None else "N/A")
    )

    if result.missing_inputs:
        lines.append("")
        lines.append("Missing")
        for idx, item in enumerate(result.missing_inputs, start=1):
            lines.append(f"{idx}. {_humanize_missing_input(item)}")

    if result.assumptions:
        lines.append("")
        lines.append("Assumptions")
        for idx, assumption in enumerate(result.assumptions, start=1):
            lines.append(f"{idx}. {assumption}")

    if result.warnings:
        lines.append("")
        lines.append("Warnings")
        for idx, warning in enumerate(result.warnings, start=1):
            lines.append(f"{idx}. {warning}")

    return "\n".join(lines)