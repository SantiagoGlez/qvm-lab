from ..analysis.overall import report_overall_score
from ..analysis.valuation import get_valuation_band_display_label
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


def usd(value: float | None, decimals: int = 2) -> str:
    """Format a float as a USD amount."""
    if value is None:
        return "-"
    return f"${value:.{decimals}f}"


def usd_billions(value: float | None, decimals: int = 1) -> str:
    """Format a USD notional in billions."""
    if value is None:
        return "-"
    return f"${value / 1e9:.{decimals}f}B"


def shares_human(value: float | None, decimals: int = 3) -> str:
    """Format shares outstanding in B/M shares."""
    if value is None:
        return "-"
    if value >= 1e9:
        return f"{value / 1e9:.{decimals}f}B"
    return f"{value / 1e6:.{decimals}f}M"


def iso_utc_timestamp(value) -> str:
    if value is None:
        return "-"
    try:
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(value)


def signed_pct(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.1f}%"


def signed_ratio_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.1%}"


def signed_billions(value: float | None) -> str:
    if value is None:
        return "N/A"
    value_bn = value / 1e9
    sign = "+" if value_bn >= 0 else "-"
    return f"{sign}{abs(value_bn):.1f}B"


def billions(value: float | None) -> str:
    """Format a float as unsigned billions."""
    if value is None:
        return "N/A"
    value_bn = value / 1e9
    return f"{abs(value_bn):.1f}B"


def pct_or_na(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1%}"


def pct_or_na_with_reason(value: float | None, reason: str | None) -> str:
    if value is not None:
        return f"{value:.1%}"
    if reason:
        return f"N/A ({reason})"
    return "N/A"


def _market_cap_delta_pct(market_cap: float | None, implied_cap: float | None) -> float | None:
    if market_cap is None or implied_cap is None or market_cap <= 0:
        return None
    return (implied_cap - market_cap) / market_cap


def _reconciliation_status(delta_pct: float | None, tolerance: float = 0.03) -> str:
    if delta_pct is None:
        return "Unavailable"
    if abs(delta_pct) <= tolerance:
        return "Aligned"
    return "Mismatch"


def _quality_tier_from_score(score: float) -> str:
    if score >= 75.0:
        return "Excellent"
    if score >= 55.0:
        return "Average"
    if score >= 35.0:
        return "Weak"
    return "Broken"


def _is_historical_valuation_supportive(valuation_band: str | None) -> bool:
    return (valuation_band or "").strip().lower() in {"deep value", "cheap", "fair value"}


def _is_major_valuation_warning(valuation_band: str | None) -> bool:
    return (valuation_band or "").strip().lower() in {"very expensive"}


def _is_intrinsic_supportive(intrinsic_assessment: str | None) -> bool:
    return (intrinsic_assessment or "").strip().lower() in {
        "very conservative expectations",
        "conservative expectations",
        "reasonable expectations",
    }


def _is_intrinsic_warning(intrinsic_assessment: str | None) -> bool:
    return (intrinsic_assessment or "").strip().lower() in {"very optimistic expectations"}


def _supports_normal_add_market(assessment: str | None) -> bool:
    return (assessment or "") in {"Attractive", "Improving"}


def _supports_slow_add_market(assessment: str | None) -> bool:
    return (assessment or "") in {"Stabilizing", "Recovering", "Neutral"}


def _valuation_confirmed_for_add(valuation_band: str | None, intrinsic_assessment: str | None) -> bool:
    historical_ok = _is_historical_valuation_supportive(valuation_band)
    intrinsic_ok = _is_intrinsic_supportive(intrinsic_assessment)
    major_warning = _is_major_valuation_warning(valuation_band)
    intrinsic_warning = _is_intrinsic_warning(intrinsic_assessment)
    return (
        (historical_ok and intrinsic_ok)
        or (historical_ok and not intrinsic_warning)
        or (intrinsic_ok and not major_warning)
    )


def _decision_path_hint(action: str, owned: bool) -> str:
    if not owned:
        if action == "Add":
            return "Tier=Excellent + valuation confirmed + market supports normal pacing."
        if action == "Add Slow":
            return "Tier=Excellent + valuation confirmed + market supports gradual pacing."
        if action == "Candidate to Add":
            return "Tier=Excellent + partial valuation support + market acceptable; reserve queue state."
        if action == "Watch":
            return "Signals are mixed; wait for better valuation/market confirmation."
        if action == "Reject":
            return "Quality/valuation warning combination fails new-capital bar."
    else:
        if action == "Add":
            return "Owned + high conviction + market supports normal add."
        if action == "Add Slow":
            return "Owned + high conviction + market supports gradual add."
        if action == "Keep (Monitor)":
            return "Owned + mild warning profile; keep with tighter monitoring."
        if action == "Review":
            return "Owned + multiple warning flags; prioritize for reassessment."
        if action == "Exit":
            return "Owned + thesis deterioration or severe warning profile."
        if action == "Keep":
            return "Owned + thesis intact; no immediate allocation change."
    return "Rule path unavailable."


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
    if v < 0:   return "Distress"
    if v >= 20: return "Excellent"
    if v >= 10: return "Strong"
    if v >= 5:  return "Good"
    if v >= 2:  return "Average"
    return "Weak"


def _label_debt_to_ebitda(v: float | None) -> str:
    if v is None: return ""
    if v < 0:   return "Weak"
    if v == 0:  return "Excellent"
    if v < 1:   return "Strong"
    if v < 2:   return "Good"
    if v < 3:   return "Average"
    return "Weak"


def _label_net_debt_to_ebitda(v: float | None, net_cash: float | None = None) -> str:
    if v is None: return ""
    if v <= 0:
        if net_cash is not None and net_cash < 0:
            return "Weak"
        if net_cash is None:
            return "Good"
        return "Excellent"
    if v < 1:   return "Strong"
    if v < 2:   return "Good"
    if v < 3:   return "Average"
    return "Weak"


def _row(label: str, value: str, tag: str = "", label_w: int = 20, value_w: int = 9) -> str:
    return f"    {label:<{label_w}}{value:>{value_w}}   {tag}"


def _section_break() -> None:
    print()
    print("-" * 60)
    print()


def _subsection_break(indent: str = "  ") -> None:
    print(f"{indent}{'-' * 42}")


def _fact(label: str, value: str, label_w: int = 24, indent: str = "") -> None:
    print(f"{indent}{label:<{label_w}}{value}")


def _capex_resilience_note(company: Company) -> str | None:
    analysis = company.capex_resilience
    if analysis.relevance == "Not Material":
        return analysis.relevance_reason or "Current capex does not appear materially elevated versus the company's normal range."
    if analysis.resilience == "High":
        return "Even if the incremental investment cycle disappoints, the existing business would still produce substantial positive free cash flow."
    if analysis.resilience == "Moderate":
        return "If elevated investment disappoints, the business still appears cash generative, but with meaningful free cash flow compression."
    if analysis.resilience == "Low":
        return "If elevated investment disappoints, free cash flow resilience appears weak and downside damage could be material."
    return analysis.resilience_reason or analysis.relevance_reason


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
    print(f"Market Cap           {usd_billions(company.metrics.market_cap)}")
    print(f"Shares Out (Reported){shares_human(company.metrics.shares_outstanding)}")
    if company.metrics.shares_outstanding_implied is not None:
        print(f"Shares Out (Implied) {shares_human(company.metrics.shares_outstanding_implied)}")
    if company.metrics.float_shares is not None:
        print(f"Float Shares         {shares_human(company.metrics.float_shares)}")
    print(f"Current Price        {usd(company.market_facts.current_price)}")

    implied_cap_reported = None
    implied_cap_implied = None
    if company.market_facts.current_price and company.metrics.shares_outstanding:
        implied_cap_reported = company.market_facts.current_price * company.metrics.shares_outstanding
    if company.market_facts.current_price and company.metrics.shares_outstanding_implied:
        implied_cap_implied = company.market_facts.current_price * company.metrics.shares_outstanding_implied

    print()
    print("Cap Check")

    if implied_cap_reported is not None:
        delta_pct = _market_cap_delta_pct(company.metrics.market_cap, implied_cap_reported)
        delta_text = f"{delta_pct:+.1%}" if delta_pct is not None else "N/A"
        _fact(
            "Implied Cap (Px x Reported)",
            f"{usd_billions(implied_cap_reported)} (delta {delta_text})",
        )

    if implied_cap_implied is not None:
        delta_pct_implied = _market_cap_delta_pct(company.metrics.market_cap, implied_cap_implied)
        delta_text_implied = f"{delta_pct_implied:+.1%}" if delta_pct_implied is not None else "N/A"
        _fact(
            "Implied Cap (Px x Implied)",
            f"{usd_billions(implied_cap_implied)} (delta {delta_text_implied})",
        )

    status = _reconciliation_status(
        _market_cap_delta_pct(company.metrics.market_cap, implied_cap_reported)
    )
    _fact("Cap Reconciliation", status)
    if status == "Mismatch":
        print("  Note: share-definition/timing mismatch is common; PE and Reverse DCF use independent inputs.")

    print()
    print("Price Context")
    print(
        "Data Basis           "
        f"Yahoo snapshot (Price/Cap/Shares) @ {iso_utc_timestamp(company.last_updated)}"
    )
    print(f"52W High             {usd(company.market_facts.price_52w_high)}")
    print(f"52W Low              {usd(company.market_facts.price_52w_low)}")
    print(f"SMA50                {usd(company.market_facts.sma_50)}")
    print(f"SMA200               {usd(company.market_facts.sma_200)}")

    _section_break()
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
    band_raw = company.valuation.valuation_band
    band_display = get_valuation_band_display_label(band_raw)
    print(f"  Valuation Band (vs history) {band_display}")
    if band_raw and band_display != band_raw:
        print(f"  Valuation Band (model)      {band_raw}")
    print()
    print("  Valuation Logs")
    print(f"    Historical Years Requested {company.valuation_facts.requested_historical_years or '-'}")
    print(f"    Valid PE Observations      {company.valuation_facts.valid_pe_count or '-'}")
    print(f"    Outliers Removed           {company.valuation_facts.outliers_removed or 0}")
    print(f"    Observations Used          {company.valuation_facts.used_pe_count or '-'}")
    if company.valuation_facts.modern_used_pe_count:
        years = company.valuation_facts.modern_regime_years or "-"
        print()
        print(f"  Modern Regime PE ({years}Y)")
        print(f"    Median                    {num(company.valuation_facts.modern_median_pe, 2)}")
        print(f"    Percentile                {pct(company.valuation_facts.modern_percentile)}")
        print(f"    Observations              {company.valuation_facts.modern_used_pe_count}")
    print()
    print(f"  Relative to Average       {signed_pct(company.valuation_facts.discount_to_average_pct)}")
    print(f"  Relative to Median        {signed_pct(company.valuation_facts.discount_to_median_pct)}")
    print("  Sign Convention          + = discount, - = premium")
    print()
    print(f"  Forward PE                {num(company.metrics.forward_pe, 2)}")
    print(f"  Trailing PE               {num(company.metrics.trailing_pe, 2)}")
    print()
    print(f"  Valuation Score           {company.valuation.score:5.1f}")

    print()

    print("Intrinsic Valuation")
    print("-" * 30)
    print()
    print("Reverse DCF")
    print()
    print(f"  Discount Rate            {company.reverse_dcf.discount_rate:.1%}")
    print(f"  Terminal Growth          {company.reverse_dcf.terminal_growth:.1%}")
    print(f"  Projection Years         {company.reverse_dcf.projection_years}")
    print()
    print(f"  Implied FCF Growth       {pct_or_na(company.reverse_dcf.implied_growth)}")
    print()
    print("Historical Growth")
    print()
    print(
        f"  Revenue CAGR 5Y          "
        f"{pct_or_na_with_reason(company.reverse_dcf.revenue_cagr_5y, company.reverse_dcf.revenue_cagr_5y_reason)}"
    )
    print(
        f"  Revenue CAGR 10Y         "
        f"{pct_or_na_with_reason(company.reverse_dcf.revenue_cagr_10y, company.reverse_dcf.revenue_cagr_10y_reason)}"
    )
    print()
    print(
        f"  EPS CAGR 5Y              "
        f"{pct_or_na_with_reason(company.reverse_dcf.eps_cagr_5y, company.reverse_dcf.eps_cagr_5y_reason)}"
    )
    print(
        f"  EPS CAGR 10Y             "
        f"{pct_or_na_with_reason(company.reverse_dcf.eps_cagr_10y, company.reverse_dcf.eps_cagr_10y_reason)}"
    )
    print()
    print(
        f"  FCF CAGR 5Y              "
        f"{pct_or_na_with_reason(company.reverse_dcf.fcf_cagr_5y, company.reverse_dcf.fcf_cagr_5y_reason)}"
    )
    print(
        f"  FCF CAGR 10Y             "
        f"{pct_or_na_with_reason(company.reverse_dcf.fcf_cagr_10y, company.reverse_dcf.fcf_cagr_10y_reason)}"
    )
    print()
    print(
        "  Growth coverage          "
        f"Revenue {company.reverse_dcf.revenue_windows_available}/2, "
        f"EPS {company.reverse_dcf.eps_windows_available}/2, "
        f"FCF {company.reverse_dcf.fcf_windows_available}/2 "
        f"({company.reverse_dcf.growth_windows_available}/6 total), "
        f"quality={company.reverse_dcf.history_quality}"
    )
    print(
        "  Growth sources           "
        f"Revenue={company.reverse_dcf.revenue_growth_source}; "
        f"EPS={company.reverse_dcf.eps_growth_source}; "
        f"FCF={company.reverse_dcf.fcf_growth_source}"
    )
    print()
    print(f"  Representative Growth    {pct_or_na(company.reverse_dcf.historical_growth_estimate)}")
    growth_cushion = company.reverse_dcf.growth_cushion
    if growth_cushion is None:
        growth_cushion = company.reverse_dcf.expectation_gap
    print(f"  Growth Cushion          {signed_ratio_pct(growth_cushion)}")
    print("  Cushion Meaning         Positive = implied growth below representative historical growth.")
    print()
    print("Assessment")
    print()
    print(f"  {company.reverse_dcf.assessment}")
    print()
    print("Notes")
    print()
    if company.reverse_dcf.representative_growth_uses_cap:
        print(
            "  - Representative Growth is winsorized before median "
            f"(cap range {company.reverse_dcf.representative_growth_cap_floor:.0%} to "
            f"{company.reverse_dcf.representative_growth_cap_ceiling:.0%})."
        )
    else:
        print("  - Representative Growth uses uncapped historical CAGR inputs.")
    print(
        "  - History quality "
        f"{company.reverse_dcf.history_quality} "
        f"(inputs={company.reverse_dcf.growth_input_count}, "
        f"dispersion={pct_or_na(company.reverse_dcf.growth_dispersion)})."
    )
    print()
    _subsection_break()
    print()
    print("Capex Resilience")
    print()
    print(f"  Relevance                {company.capex_resilience.relevance}")
    if company.capex_resilience.relevance_reason:
        print(f"  Relevance Reason         {company.capex_resilience.relevance_reason}")

    if company.capex_resilience.relevance != "Not Material":
        print()
        print("Current Burden")
        print()
        print(f"  Capex / Revenue          {pct_or_na(company.capex_resilience.capex_to_revenue)}")
        print(f"  Capex / CFO              {pct_or_na(company.capex_resilience.capex_to_cfo)}")
        print(f"  FCF Margin               {pct_or_na(company.capex_resilience.fcf_margin)}")
        net_cash_to_capex = company.capex_resilience.net_cash_to_capex
        if net_cash_to_capex is None:
            print("  Net Cash / Capex         N/A")
        else:
            print(f"  Net Cash / Capex         {net_cash_to_capex:.1f}x")

        print()
        print("Historical Baseline")
        print()
        years_used = company.capex_resilience.historical_years_used
        baseline_label = f"{years_used}Y median" if years_used else "limited history"
        print(
            f"  Historical Capex/Rev     {pct_or_na(company.capex_resilience.historical_capex_to_revenue_median)} "
            f"({baseline_label})"
        )
        print(f"  Excess Capex             {signed_billions(company.capex_resilience.excess_capex)}")

        print()
        print("Failed Incremental Capex")
        print()
        print(f"  Stress FCF Impact        {signed_billions(company.capex_resilience.stress_fcf_impact)}")
        print(f"  Stress FCF               {signed_billions(company.capex_resilience.stress_free_cash_flow)}")
        print(f"  Stress FCF Margin        {pct_or_na(company.capex_resilience.stress_fcf_margin)}")

        print()
        print("Assessment")
        print()
        print(f"  {company.capex_resilience.resilience}")
    else:
        print(f"  Note                     {_capex_resilience_note(company) or '-'}")

    capex_note = _capex_resilience_note(company)
    if company.capex_resilience.relevance != "Not Material" and capex_note:
        print()
        print("Notes")
        print()
        print("  - Stress assumes capex above the historical normal level produces no incremental return.")
        print("  - This is an analytical downside overlay, not a forecast or score.")
        print(f"  - {capex_note}")
    print()

    _section_break()
    print(f"Quality              {company.quality.score:5.1f}")
    print(f"  Coverage            {company.quality.coverage:.0%}")
    if company.quality.coverage < 1.0:
        missing = ", ".join(company.quality.missing_metrics) if company.quality.missing_metrics else "None"
        print(f"  Missing             {missing}")
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
    net_debt_label = _label_net_debt(company.metrics.net_debt_ebitda, company.metrics.net_cash)
    if company.metrics.net_cash is not None:
        if company.metrics.net_cash >= 0:
            print(_row("Net Cash (Cash-Debt)", signed_billions(company.metrics.net_cash), ""))
        else:
            print(_row("Net Debt (Debt-Cash)", billions(company.metrics.net_cash), ""))
    else:
        print(_row("Net Cash (Cash-Debt)", "N/A", ""))

    if company.metrics.net_debt_ebitda is not None:
        print(
            _row(
                "Net Debt/EBITDA",
                f"{company.metrics.net_debt_ebitda:.2f}x",
                _label_net_debt_to_ebitda(company.metrics.net_debt_ebitda, company.metrics.net_cash),
            )
        )

    if company.metrics.debt_to_ebitda is not None:
        print(_row("Debt/EBITDA", f"{company.metrics.debt_to_ebitda:.1f}x", _label_debt_to_ebitda(company.metrics.debt_to_ebitda)))

    if company.metrics.interest_coverage is not None:
        print(_row("Interest Coverage", f"{company.metrics.interest_coverage:.1f}x", _label_interest_coverage(company.metrics.interest_coverage)))
    elif company.metrics.debt_to_ebitda is None and company.metrics.net_debt_ebitda is None:
        print(_row("Interest Coverage", "-", ""))
    print("    Note: Net Debt = Debt - Cash; positive means net debt, negative means net cash.")

    _section_break()

    print(f"Overall              {report_overall_score(company):5.1f}")

    _section_break()
    # --- Portfolio -----------------------------------------------------------
    p = company.portfolio
    position_label = "Owned" if p.owned else "Not owned"
    print("Portfolio")
    print()
    print(f"  {'Position':<22}{position_label}")
    print(f"  {'Action':<22}{p.action or '-'}")

    tier = _quality_tier_from_score(company.quality.score)
    valuation_band = company.valuation.valuation_band
    intrinsic_assessment = company.reverse_dcf.assessment
    market_assessment = company.momentum.recommendation
    historical_supportive = _is_historical_valuation_supportive(valuation_band)
    intrinsic_supportive = _is_intrinsic_supportive(intrinsic_assessment)
    valuation_confirmed = _valuation_confirmed_for_add(valuation_band, intrinsic_assessment)
    market_normal = _supports_normal_add_market(market_assessment)
    market_slow = _supports_slow_add_market(market_assessment)

    print()
    print("  Decision Rules")
    print(f"    Quality Score              {company.quality.score:.1f} (tier={tier}; Excellent>=75, Average>=55, Weak>=35)")
    print(f"    Historical Valuation       {valuation_band or '-'} (supportive={historical_supportive})")
    print(f"    Intrinsic Assessment       {intrinsic_assessment or '-'} (supportive={intrinsic_supportive})")
    print(f"    Valuation Confirmed        {valuation_confirmed}")
    print(f"    Market Assessment          {market_assessment or '-'} (normal_add={market_normal}; slow_add={market_slow})")
    print(f"    Rule Path                  {_decision_path_hint(p.action or '', p.owned)}")

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
    _section_break()
    print("Market")
    print()
    sig = company.momentum
    mf = company.market_facts

    print("  Price Context")
    print(f"  {'Current Price':<22}{usd(mf.current_price)}")
    print(f"  {'52W High':<22}{usd(mf.price_52w_high)}")
    print(f"  {'52W Low':<22}{usd(mf.price_52w_low)}")
    print(f"  {'Distance from 52W High':<24}{signed_ratio_pct(mf.distance_from_52w_high_pct)}")
    print(f"  {'Distance from 52W Low':<24}{signed_ratio_pct(mf.distance_from_52w_low_pct)}")
    print(f"  {'SMA50':<22}{usd(mf.sma_50)}")
    print(f"  {'SMA200':<22}{usd(mf.sma_200)}")
    print()

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

