from ..analysis.overall import overall_score
from ..models import Company


def pct(value: float | None) -> str:
    """Format a float as a percentage."""
    if value is None:
        return "-"
    return f"{value:.1%}"


def num(value: float | None, decimals: int = 1) -> str:
    """Format a float."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def signed_pct(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.1f}%"


# ---------------------------------------------------------------------------
# Qualitative label helpers — thresholds centralized here for easy tuning
# ---------------------------------------------------------------------------

def _label_roic(v: float | None) -> str:
    if v is None: return ""
    v *= 100
    if v >= 25: return "Excellent"
    if v >= 15: return "Strong"
    if v >= 10: return "Good"
    if v >= 5:  return "Average"
    return "Weak"


def _label_roe(v: float | None) -> str:
    if v is None: return ""
    v *= 100
    if v >= 30: return "Excellent"
    if v >= 20: return "Strong"
    if v >= 15: return "Good"
    if v >= 10: return "Average"
    return "Weak"


def _label_operating_margin(v: float | None) -> str:
    if v is None: return ""
    v *= 100
    if v >= 30: return "Excellent"
    if v >= 20: return "Strong"
    if v >= 10: return "Good"
    if v >= 5:  return "Average"
    return "Weak"


def _label_cagr(v: float | None) -> str:
    if v is None: return ""
    v *= 100
    if v >= 15: return "Excellent"
    if v >= 10: return "Strong"
    if v >= 5:  return "Good"
    if v >= 0:  return "Flat"
    return "Weak"


def _label_fcf_margin(v: float | None) -> str:
    if v is None: return ""
    v *= 100
    if v >= 25: return "Excellent"
    if v >= 15: return "Strong"
    if v >= 8:  return "Good"
    if v >= 3:  return "Average"
    return "Weak"


def _label_fcf_conversion(v: float | None) -> str:
    if v is None: return ""
    v *= 100
    if v >= 100: return "Excellent"
    if v >= 80:  return "Strong"
    if v >= 60:  return "Good"
    if v >= 40:  return "Average"
    return "Weak"


def _label_net_debt(net_debt_ebitda: float | None, net_cash: float | None) -> str:
    if net_cash is not None and net_cash > 0:
        return "Excellent"
    if net_debt_ebitda is None: return ""
    if net_debt_ebitda < 1: return "Strong"
    if net_debt_ebitda < 2: return "Good"
    if net_debt_ebitda < 3: return "Average"
    return "Weak"


def _label_interest_coverage(v: float | None) -> str:
    if v is None: return ""
    if v >= 20: return "Excellent"
    if v >= 10: return "Strong"
    if v >= 5:  return "Good"
    if v >= 2:  return "Average"
    return "Weak"


def _label_debt_to_ebitda(v: float | None) -> str:
    if v is None: return ""
    if v <= 0:  return "Excellent"
    if v < 1:   return "Strong"
    if v < 2:   return "Good"
    if v < 3:   return "Average"
    return "Weak"


def _row(label: str, value: str, tag: str = "", label_w: int = 20, value_w: int = 9) -> str:
    return f"    {label:<{label_w}}{value:>{value_w}}   {tag}"


def print_report(company: Company) -> None:

    print()

    print("=" * 60)
    print(company.name or company.ticker)
    print("=" * 60)

    print()

    print(f"Ticker               {company.ticker}")
    print(f"Sector               {company.sector or '-'}")
    print(f"Industry             {company.industry or '-'}")

    print()
    print("Metrics")
    print("-" * 30)

    print(f"Forward PE           {num(company.metrics.forward_pe, 2)}")
    print(f"Trailing PE          {num(company.metrics.trailing_pe, 2)}")
    print(f"Market Cap           {company.metrics.market_cap or '-'}")

    print()
    print("Analysis")
    print("-" * 30)

    print("Valuation")
    # Current PE is a live daily value (Yahoo: Price / TTM EPS).
    # Historical PEs are annual year-end snapshots from CompaniesMarketCap CSV.
    # Comparing a daily PE against an annual series is intentional — the live
    # price is what matters for today's entry point — but be aware that large
    # divergences (e.g. >30%) may reflect earnings growth since the last CSV
    # scrape rather than a true valuation change.
    print(f"  Current PE                {num(company.valuation_facts.current_pe, 2)}")
    print(f"  Current PE Source         {company.valuation_facts.current_pe_source or 'CSV (last annual)'}")
    print(f"  Historical Average PE     {num(company.valuation_facts.historical_average_pe, 2)}")
    print(f"  Historical Median PE      {num(company.valuation_facts.historical_median_pe, 2)}")
    print(f"  Historical Percentile     {pct(company.valuation_facts.historical_percentile)}")
    print(f"  Valuation Band            {company.valuation.valuation_band or '-'}")
    print()
    print("  Valuation Logs")
    print(f"    Historical Years Requested {company.valuation_facts.requested_historical_years or '-'}")
    print(f"    Valid PE Observations      {company.valuation_facts.valid_pe_count or '-'}")
    print(f"    Outliers Removed           {company.valuation_facts.outliers_removed or 0}")
    print(f"    Observations Used          {company.valuation_facts.used_pe_count or '-'}")
    print()
    print(f"  Discount to Average       {signed_pct(company.valuation_facts.discount_to_average_pct)}")
    print(f"  Discount to Median        {signed_pct(company.valuation_facts.discount_to_median_pct)}")
    print()
    print(f"  Forward PE                {num(company.metrics.forward_pe, 2)}")
    print(f"  Trailing PE               {num(company.metrics.trailing_pe, 2)}")
    print()
    print(f"  Valuation Score           {company.valuation.score:5.1f}")

    print()

    print(f"Quality              {company.quality.score:5.1f}")
    print()
    print("Evaluate the long-term quality and valuation of the business.")
    print()
    print(_row("ROIC",             pct(company.metrics.roic),             _label_roic(company.metrics.roic)))
    print(_row("ROE",              pct(company.metrics.roe),              _label_roe(company.metrics.roe)))
    print(_row("Operating Margin", pct(company.metrics.operating_margin), _label_operating_margin(company.metrics.operating_margin)))

    print("  Growth")
    rev_tag = f"({company.metrics.revenue_cagr_years}Y)" if company.metrics.revenue_cagr_years else ""
    eps_tag = f"({company.metrics.eps_cagr_years}Y)" if company.metrics.eps_cagr_years else ""
    print(_row(f"Revenue CAGR {rev_tag}", pct(company.metrics.revenue_cagr), _label_cagr(company.metrics.revenue_cagr)))
    print(_row(f"EPS CAGR {eps_tag}",     pct(company.metrics.eps_cagr),     _label_cagr(company.metrics.eps_cagr)))

    print("  Cash Generation")
    print(_row("FCF Margin",      pct(company.metrics.fcf_margin),      _label_fcf_margin(company.metrics.fcf_margin)))
    print(_row("FCF Conversion",  pct(company.metrics.fcf_conversion),  _label_fcf_conversion(company.metrics.fcf_conversion)))

    print("  Financial Strength")
    net_cash_bn = company.metrics.net_cash / 1e9 if company.metrics.net_cash is not None else None
    net_debt_label = _label_net_debt(company.metrics.net_debt_ebitda, company.metrics.net_cash)
    if net_cash_bn is not None and net_cash_bn > 0:
        print(_row("Net Cash",  f"+{net_cash_bn:.1f}B", net_debt_label))
    elif net_cash_bn is not None and net_cash_bn < 0:
        print(_row("Net Debt",  f"{abs(net_cash_bn):.1f}B", net_debt_label))
    else:
        print(_row("Net Cash/Debt", "N/A", ""))
    if company.metrics.interest_coverage is not None:
        print(_row("Interest Coverage", f"{company.metrics.interest_coverage:.1f}x", _label_interest_coverage(company.metrics.interest_coverage)))
    elif company.metrics.debt_to_ebitda is not None:
        print(_row("Debt/EBITDA", f"{company.metrics.debt_to_ebitda:.1f}x", _label_debt_to_ebitda(company.metrics.debt_to_ebitda)))
    else:
        print(_row("Interest Coverage", "-", ""))

    print()

    print("-" * 30)

    print(f"Overall              {overall_score(company):5.1f}")

    print()

    # --- Portfolio -----------------------------------------------------------
    p = company.portfolio
    position_label = "Owned" if p.owned else "Not owned"
    print("Portfolio")
    print()
    print("Recommend the appropriate portfolio action based on the company fundamentals, current market conditions, and whether the stock is already owned.")
    print()
    print(f"  {'Position':<22}{position_label}")
    print(f"  {'Action':<22}{p.action or '-'}")

    def _wrap(text: str, indent: str = "    ", width: int = 60) -> None:
        words = text.split()
        line, lines = "", []
        for word in words:
            if len(line) + len(word) + 1 > width:
                lines.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            lines.append(line)
        for l in lines:
            print(f"{indent}{l}")

    if p.company_reason:
        print()
        print("  Company")
        _wrap(p.company_reason)
    if p.market_reason:
        print()
        print("  Market")
        _wrap(p.market_reason)
    if p.portfolio_reason:
        print()
        print("  Portfolio")
        _wrap(p.portfolio_reason)
    print()

    print("Market")
    print()
    print("Assess whether current price action provides an attractive entry or management point.")
    print()
    sig = company.momentum

    _sig_map: dict[str, str] = {}
    for part in (sig.summary or "").split(" | "):
        if "=" in part:
            k, v = part.split("=", 1)
            _sig_map[k.strip()] = v.strip()

    print(f"  {'Trend':<22}{_sig_map.get('Trend', '-')}")
    print(f"  {'Relative Strength':<22}{_sig_map.get('RS', '-')}")
    print(f"  {'Pullback':<22}{_sig_map.get('Pullback', '-')}")
    print()
    print(f"  Assessment")
    print(f"    {sig.recommendation or '-'}")
    print()
    if sig.reason:
        print(f"  Reason")
        words = sig.reason.split()
        line, lines = "", []
        for word in words:
            if len(line) + len(word) + 1 > 60:
                lines.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            lines.append(line)
        for l in lines:
            print(f"    {l}")
    print()

