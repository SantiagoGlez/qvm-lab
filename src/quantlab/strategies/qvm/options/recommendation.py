from __future__ import annotations

from typing import Any

from quantlab.strategies.qvm.models import Company
from quantlab.strategies.qvm.reports.google_finance_chat import run_google_finance_audit


def _confidence_label(score: float) -> str:
    if score >= 0.90:
        return "high"
    if score >= 0.80:
        return "medium"
    return "low"


def _option_market_quality(
    option_market_data: dict[str, dict[str, float]] | None,
    ticker: str,
) -> tuple[bool, str, float | None, float | None, float | None]:
    if option_market_data is None:
        return True, "controlled", None, None, None

    metrics = option_market_data.get(ticker.upper(), {})
    iv = float(metrics.get("iv", 0.0) or 0.0)
    volume = float(metrics.get("volume", 0.0) or 0.0)
    open_interest = float(metrics.get("open_interest", 0.0) or 0.0)

    liquidity_ok = True
    if iv > 0.90:
        liquidity_ok = False
    if volume > 0 and volume < 250_000:
        liquidity_ok = False
    if open_interest > 0 and open_interest < 1_000:
        liquidity_ok = False

    if iv > 0.90 or volume > 0 and volume < 250_000 or open_interest > 0 and open_interest < 1_000:
        risk_level = "aggressive"
    elif iv > 0.70 or volume > 0 and volume < 1_000_000 or open_interest > 0 and open_interest < 5_000:
        risk_level = "cautious"
    else:
        risk_level = "controlled"

    return liquidity_ok, risk_level, iv, volume, open_interest


def _strike_from_price(price: float, maturity_months: int) -> float:
    if maturity_months == 6:
        premium_pct = 0.08
    elif maturity_months == 9:
        premium_pct = 0.10
    else:
        premium_pct = 0.12
    return round(float(price * (1.0 + premium_pct)), 2)


def finalize_trade_decision(
    recommendation: dict[str, Any],
    *,
    google_finance_verdict: str | None = None,
) -> dict[str, Any]:
    """Apply a final go/watch/reject gate using liquidity, risk, and external audit data."""
    updated = dict(recommendation)
    liquidity_ok = bool(updated.get("liquidity_ok", True))
    risk_level = str(updated.get("risk_level", "controlled")).lower()
    verdict = (google_finance_verdict or updated.get("google_finance_verdict") or "").strip()
    normalized_verdict = verdict.lower()

    if not liquidity_ok:
        updated["decision"] = "reject"
        updated["decision_reason"] = "Reject: option chain is too illiquid for a controlled call trade."
        return updated

    if normalized_verdict == "fail":
        updated["decision"] = "reject"
        updated["decision_reason"] = "Reject: Google Finance audit failed the thesis guardrail."
        return updated

    if normalized_verdict == "pass with caveats":
        updated["decision"] = "watch" if risk_level == "aggressive" else "watch"
        updated["decision_reason"] = (
            "Watch: the thesis is intact but the Google Finance audit includes caveats and risk controls "
            "must stay strict."
        )
        return updated

    if normalized_verdict == "pass":
        if risk_level == "aggressive":
            updated["decision"] = "watch"
            updated["decision_reason"] = (
                "Watch: the external audit is supportive, but the option risk profile is still aggressive."
            )
        else:
            updated["decision"] = "approve"
            updated["decision_reason"] = (
                "Approve: stock screen, option quality, and Google Finance validation are aligned."
            )
        return updated

    if risk_level == "aggressive":
        updated["decision"] = "watch"
        updated["decision_reason"] = "Watch: the call may be valid, but the risk profile is too aggressive without external validation."
        return updated

    updated["decision"] = "approve"
    updated["decision_reason"] = "Approve: the trade is aligned with the QVM screen and keeps risk within budget."
    return updated


def build_call_recommendation(
    company: Company,
    *,
    maturity_months: int = 9,
    score: float | None = None,
    risk_budget_pct: float = 0.02,
    option_market_data: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Create a trade-level directional call recommendation from a screened company."""
    current_price = float(getattr(company.market_facts, "current_price", 0.0) or 0.0)
    if current_price <= 0:
        raise ValueError(f"Current price is required to build a call recommendation for {company.ticker}")

    quality_score = float(getattr(getattr(company, "quality", None), "score", 0.0) or 0.0)
    confidence_score = float(score if score is not None else max(quality_score / 100.0, 0.0))
    liquidity_ok, risk_level, iv, volume, open_interest = _option_market_quality(option_market_data, company.ticker)

    suggested_strike = _strike_from_price(current_price, maturity_months)
    max_loss = round(float(current_price * risk_budget_pct), 2)
    break_even = round(float(suggested_strike + max_loss), 2)
    target = round(
        float(current_price * (1.0 + (0.18 if maturity_months <= 6 else 0.22 if maturity_months <= 9 else 0.28))),
        2,
    )
    stop = round(float(current_price * 0.92), 2)
    delta_target = {6: 0.55, 9: 0.50, 12: 0.45}.get(maturity_months, 0.50)

    thesis = (
        f"Directional call on {company.name or company.ticker} driven by quality, "
        f"intrinsic valuation ({getattr(company.reverse_dcf, 'assessment', 'Unavailable')}), "
        f"and improving market conditions."
    )

    if not liquidity_ok:
        trade_status = "liquidity warning: avoid or defer until option chain improves"
    else:
        trade_status = "eligible trade: option chain acceptable for a directional call"

    recommendation = {
        "ticker": company.ticker,
        "name": company.name or company.ticker,
        "current_price": current_price,
        "maturity_months": int(maturity_months),
        "thesis": thesis,
        "suggested_strike": suggested_strike,
        "delta_target": delta_target,
        "max_loss": max_loss,
        "break_even": break_even,
        "target": target,
        "stop_loss": stop,
        "confidence": _confidence_label(confidence_score),
        "liquidity_ok": liquidity_ok,
        "risk_level": risk_level,
        "trade_status": trade_status,
        "iv": iv,
        "volume": volume,
        "open_interest": open_interest,
    }
    return finalize_trade_decision(recommendation)


def build_call_recommendations(
    companies: list[Company],
    screened_candidates: list[dict[str, Any]],
    option_market_data: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    company_by_ticker = {company.ticker.upper(): company for company in companies}
    recommendations: list[dict[str, Any]] = []

    for row in screened_candidates:
        ticker = str(row.get("ticker", "")).upper()
        company = company_by_ticker.get(ticker)
        if company is None:
            continue
        recommendation = build_call_recommendation(
            company,
            maturity_months=int(row.get("maturity_months", 9)),
            score=float(row.get("score", 0.0) or 0.0),
            option_market_data=option_market_data,
        )
        recommendations.append(recommendation)

    return recommendations


def build_trade_audit_text(company: Company, recommendation: dict[str, Any]) -> str:
    lines = [
        "QVM call trade audit summary",
        f"Ticker: {company.ticker}",
        f"Company: {company.name or company.ticker}",
        f"Current price: {recommendation.get('current_price', 'n/a')}",
        f"Maturity months: {recommendation.get('maturity_months', 'n/a')}",
        f"Quality score: {getattr(getattr(company, 'quality', None), 'score', 'n/a')}",
        f"Intrinsic valuation: {getattr(company.reverse_dcf, 'assessment', 'Unavailable')}",
        f"Historical valuation: {getattr(company.valuation, 'valuation_band', 'Unavailable')}",
        f"Market assessment: {getattr(company.momentum, 'recommendation', 'Unknown')}",
        f"Portfolio action: {getattr(getattr(company, 'portfolio', None), 'action', '')}",
        f"Thesis: {recommendation.get('thesis', '')}",
        f"Suggested strike: {recommendation.get('suggested_strike', 'n/a')}",
        f"Break-even: {recommendation.get('break_even', 'n/a')}",
        f"Target: {recommendation.get('target', 'n/a')}",
        f"Stop: {recommendation.get('stop_loss', 'n/a')}",
        f"Confidence: {recommendation.get('confidence', 'n/a')}",
        f"Risk level: {recommendation.get('risk_level', 'n/a')}",
        f"Liquidity acceptable: {recommendation.get('liquidity_ok', 'n/a')}",
        f"Trade status: {recommendation.get('trade_status', 'n/a')}",
    ]
    return "\n".join(lines)


def validate_recommendation_with_google_finance(
    company: Company,
    recommendation: dict[str, Any],
    *,
    mode: str = "quick",
    timeout_seconds: int = 120,
    headless: bool = True,
) -> dict[str, Any]:
    report_text = build_trade_audit_text(company, recommendation)
    audit_result = run_google_finance_audit(
        report_text,
        mode=mode,
        timeout_seconds=timeout_seconds,
        headless=headless,
    )

    verdict = ""
    if audit_result.success and audit_result.response:
        for line in audit_result.response.splitlines():
            if line.lower().startswith("verdict:"):
                verdict = line.split(":", 1)[1].strip()
                break
    if not verdict:
        verdict = "Unknown"

    result = {
        "ticker": company.ticker,
        "google_finance_success": audit_result.success,
        "google_finance_verdict": verdict,
        "google_finance_response": audit_result.response,
        "google_finance_error": audit_result.error,
        "audit_prompt": report_text,
    }
    if recommendation:
        finalized = finalize_trade_decision(recommendation, google_finance_verdict=verdict)
        result.update({
            "decision": finalized.get("decision"),
            "decision_reason": finalized.get("decision_reason"),
        })
    return result
