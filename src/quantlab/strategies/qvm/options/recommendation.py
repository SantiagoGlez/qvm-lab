from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf

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


def _risk_level_reason(
    risk_level: str,
    *,
    weak_liquidity: bool = False,
    iv: float | None = None,
    volume: float | None = None,
    open_interest: float | None = None,
) -> str:
    if weak_liquidity:
        return "live option chain exists but the rows are illiquid: low volume, low open interest, or wide spread"

    reasons: list[str] = []
    if iv is not None and iv > 0.90:
        reasons.append("implied volatility is very high")
    if volume is not None and volume > 0 and volume < 250_000:
        reasons.append("volume is low")
    if open_interest is not None and open_interest > 0 and open_interest < 1_000:
        reasons.append("open interest is low")

    if reasons:
        return "; ".join(reasons)
    if risk_level == "aggressive":
        return "the option mix is elevated-risk despite acceptable structure"
    if risk_level == "cautious":
        return "the trade is valid but not fully comfortable on liquidity and risk control"
    return "the option profile is within a normal risk range"


def _is_option_row_acceptable(
    row: dict[str, float],
    current_price: float,
    target_delta: float,
    maturity_months: int,
) -> bool:
    strike = float(row["strike"])
    bid = float(row["bid"])
    ask = float(row["ask"])
    volume = float(row["volume"])
    open_interest = float(row["open_interest"])
    delta = float(row["delta"])
    distance_pct = abs(strike - current_price) / max(current_price, 1.0)
    spread_pct = (ask - bid) / max(ask, 0.01) if bid > 0 and ask > 0 else 1.0
    max_distance = {6: 0.10, 9: 0.12, 12: 0.15}.get(maturity_months, 0.12)
    delta_band = {6: 0.18, 9: 0.20, 12: 0.22}.get(maturity_months, 0.20)

    if volume < 100 or open_interest < 100:
        return False
    if spread_pct > 0.10:
        return False
    if distance_pct > max_distance:
        return False
    if abs(delta - target_delta) > delta_band:
        return False
    return True


def estimate_best_call_contract(
    ticker: str,
    current_price: float,
    maturity_months: int,
    *,
    target_delta: float | None = None,
    ignore_liquidity: bool = False,
) -> dict[str, Any]:
    """Estimate a realistic call-contract strike using the live option chain when available.

    This keeps a conservative fallback when no option-chain data is available.
    """
    target_delta = target_delta if target_delta is not None else {6: 0.55, 9: 0.50, 12: 0.45}.get(maturity_months, 0.50)

    try:
        stock = yf.Ticker(ticker)
        expiries = list(getattr(stock, "options", []) or [])
        if not expiries:
            raise ValueError("No option expiries available")

        history = stock.history(period="1d")
        if history.empty:
            raise ValueError("No recent price history available for option-chain estimation")

        latest_history_ts = pd.Timestamp(history.index[-1]).tz_localize(None) if pd.Timestamp(history.index[-1]).tzinfo is not None else pd.Timestamp(history.index[-1])
        target_expiry = min(
            expiries,
            key=lambda expiry: abs(
                float((pd.to_datetime(expiry).tz_localize(None) - latest_history_ts).days) / 30.4375 - maturity_months
            ),
        )
        chain = stock.option_chain(target_expiry)
        calls = getattr(chain, "calls", None)
        if calls is None or getattr(calls, "empty", True):
            raise ValueError("No calls in option chain")

        rows = []
        best_raw = None
        for row in calls.itertuples(index=False):
            strike = float(getattr(row, "strike", 0.0) or 0.0)
            if strike <= 0:
                continue
            delta = float(getattr(row, "delta", target_delta) or target_delta)
            bid = float(getattr(row, "bid", 0.0) or 0.0)
            ask = float(getattr(row, "ask", 0.0) or 0.0)
            last = float(getattr(row, "lastPrice", 0.0) or 0.0)
            volume = float(getattr(row, "volume", 0.0) or 0.0)
            open_interest = float(getattr(row, "openInterest", 0.0) or 0.0)
            premium = last if last > 0 else ((bid + ask) / 2.0 if bid > 0 or ask > 0 else 0.0)

            candidate = {
                "strike": strike,
                "delta": delta,
                "premium": premium,
                "break_even": strike + premium,
                "volume": volume,
                "open_interest": open_interest,
                "bid": bid,
                "ask": ask,
            }
            distance_factor = abs(strike - current_price) / max(current_price, 1.0)
            delta_gap = abs(delta - target_delta)
            liquidity_penalty = 0.0
            if volume < 100 or open_interest < 100:
                liquidity_penalty += 0.05
            if bid > 0 and ask > 0:
                spread = ask - bid
                liquidity_penalty += min(spread / max(current_price * 0.05, 0.01), 0.10)
            candidate["score"] = delta_gap + distance_factor + liquidity_penalty
            if best_raw is None or candidate["score"] < best_raw["score"]:
                best_raw = candidate
            if not ignore_liquidity and not _is_option_row_acceptable(candidate, current_price, target_delta, maturity_months):
                continue
            rows.append(candidate)

        if not rows:
            if best_raw is None:
                raise ValueError("No viable call rows")
            return {
                "source": "live_chain",
                "strike": round(float(best_raw["strike"]), 2),
                "delta": round(float(best_raw["delta"]), 3),
                "premium_estimate": round(float(best_raw["premium"]), 4),
                "break_even": round(float(best_raw["break_even"]), 2),
                "volume": int(best_raw["volume"]),
                "open_interest": int(best_raw["open_interest"]),
                "bid": round(float(best_raw["bid"]), 4),
                "ask": round(float(best_raw["ask"]), 4),
                "expiry": target_expiry,
                "target_delta": round(float(target_delta), 3),
                "selected_row": best_raw,
                "weak_liquidity": True,
                "fallback_reason": "live option chain exists but all rows are too illiquid for the standard acceptance gate",
            }

        best = min(rows, key=lambda row: row["score"])
        return {
            "source": "live_chain",
            "strike": round(float(best["strike"]), 2),
            "delta": round(float(best["delta"]), 3),
            "premium_estimate": round(float(best["premium"]), 4),
            "break_even": round(float(best["break_even"]), 2),
            "volume": int(best["volume"]),
            "open_interest": int(best["open_interest"]),
            "bid": round(float(best["bid"]), 4),
            "ask": round(float(best["ask"]), 4),
            "expiry": target_expiry,
            "target_delta": round(float(target_delta), 3),
            "selected_row": best,
        }
    except Exception as exc:
        strike = _strike_from_price(current_price, maturity_months)
        fallback_reason = f"fallback because live option chain is unavailable or incomplete: {type(exc).__name__}"
        return {
            "source": "heuristic",
            "strike": strike,
            "delta": round(float(target_delta), 3),
            "premium_estimate": round(float(abs(strike - current_price) * 0.05), 4),
            "break_even": round(float(strike + abs(strike - current_price) * 0.05), 2),
            "volume": 0,
            "open_interest": 0,
            "bid": 0.0,
            "ask": 0.0,
            "expiry": None,
            "target_delta": round(float(target_delta), 3),
            "fallback_reason": fallback_reason,
        }


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

    if updated.get("estimated_option_source") == "heuristic":
        if normalized_verdict == "fail":
            updated["decision"] = "reject"
            updated["decision_reason"] = "Reject: heuristic fallback is not enough to support the trade after external validation failed."
            return updated

        updated["decision"] = "watch"
        updated["decision_reason"] = (
            "Watch: the recommendation used a heuristic option estimate because the live option chain was unavailable. "
            "Do not treat this as fully validated trade execution."
        )
        return updated

    if not liquidity_ok and not updated.get("ignore_liquidity", False):
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


def build_call_payoff_table(
    current_price: float,
    strike: float,
    premium: float,
    *,
    target: float | None = None,
    break_even: float | None = None,
    contract_multiplier: int = 100,
) -> list[dict[str, float]]:
    """Return a small payoff grid for a long call so the detail view shows profit at key prices."""
    target = float(target) if target is not None else float(current_price * 1.22)
    break_even = float(break_even) if break_even is not None else float(strike + premium)
    direct_stock_cash = float(premium * contract_multiplier)
    equivalent_shares = direct_stock_cash / max(current_price, 0.01)
    reference_prices = {
        round(float(current_price * 0.90), 2),
        round(float(current_price * 0.95), 2),
        round(float(current_price), 2),
        round(float(strike), 2),
        round(float(break_even), 2),
        round(float(target), 2),
        round(float(current_price * 1.10), 2),
    }
    if target > break_even:
        mid_between_be_and_target = round(float((break_even + target) / 2.0), 2)
        reference_prices.add(mid_between_be_and_target)
    reference_prices = sorted(reference_prices)
    rows: list[dict[str, float]] = []
    for stock_price in reference_prices:
        intrinsic_value = max(stock_price - strike, 0.0)
        profit_per_share = intrinsic_value - premium
        profit_contract = float(profit_per_share * contract_multiplier)
        profit_contract_pct = ((profit_per_share / max(premium, 0.01)) * 100.0) if premium > 0 else 0.0
        stock_direct_profit = (stock_price - current_price) * equivalent_shares
        pct_move = ((stock_price - current_price) / max(current_price, 0.01)) * 100.0
        rows.append(
            {
                "stock_price": round(float(stock_price), 2),
                "pct_move": round(float(pct_move), 2),
                "intrinsic_value": round(float(intrinsic_value), 2),
                "profit_per_share": round(float(profit_per_share), 2),
                "profit_contract": round(float(profit_contract), 2),
                "profit_contract_pct": round(float(profit_contract_pct), 2),
                "stock_direct_profit": round(float(stock_direct_profit), 2),
            }
        )
    return rows


def build_standalone_call_report(
    ticker: str,
    *,
    current_price: float | None = None,
    maturity_months: int = 9,
    target_delta: float | None = None,
    ignore_liquidity: bool = False,
) -> dict[str, Any]:
    """Create a raw call trade report for any ticker without QVM company screening."""
    if current_price is None:
        history = yf.Ticker(ticker).history(period="1d")
        if history.empty:
            raise ValueError(f"No market price available for {ticker}")
        current_price = float(history["Close"].iloc[-1])

    option_estimate = estimate_best_call_contract(
        ticker,
        float(current_price),
        maturity_months,
        target_delta=target_delta,
        ignore_liquidity=ignore_liquidity,
    )
    strike = float(option_estimate["strike"])
    premium_estimate = float(option_estimate.get("premium_estimate", 0.0) or 0.0)
    premium_pct_of_stock = round(float((premium_estimate / max(current_price, 0.01)) * 100.0), 2) if premium_estimate > 0 else 0.0
    target = round(float(current_price * (1.0 + (0.18 if maturity_months <= 6 else 0.22 if maturity_months <= 9 else 0.28))), 2)
    target_move_pct = round(float(((target - current_price) / max(current_price, 0.01)) * 100.0), 2)
    stop_loss = round(float(current_price * 0.92), 2)
    break_even = round(float(option_estimate.get("break_even", strike + premium_estimate)), 2)
    break_even_pct = round(float(((break_even - current_price) / max(current_price, 0.01)) * 100.0), 2)
    risk_level = "controlled"
    if option_estimate.get("source") == "heuristic":
        risk_level = "cautious"
    if option_estimate.get("source") == "live_chain":
        selected_row = option_estimate.get("selected_row") or {}
        if selected_row.get("volume", 0) < 1000 or selected_row.get("open_interest", 0) < 1000:
            risk_level = "cautious"
    weak_liquidity = bool(option_estimate.get("weak_liquidity", False))
    risk_level_reason = _risk_level_reason(
        risk_level,
        weak_liquidity=weak_liquidity,
        iv=None,
        volume=float(selected_row.get("volume", 0.0) or 0.0) if (selected_row := option_estimate.get("selected_row") or {}) else None,
        open_interest=float(selected_row.get("open_interest", 0.0) or 0.0) if selected_row else None,
    )

    report = {
        "ticker": ticker.upper(),
        "current_price": float(current_price),
        "maturity_months": int(maturity_months),
        "estimated_option_source": option_estimate.get("source", "heuristic"),
        "suggested_strike": strike,
        "delta_target": option_estimate.get("target_delta", target_delta or {6: 0.55, 9: 0.50, 12: 0.45}.get(maturity_months, 0.50)),
        "premium_estimate": premium_estimate,
        "break_even": break_even,
        "target": target,
        "stop_loss": stop_loss,
        "premium_pct_of_stock": premium_pct_of_stock,
        "target_move_pct": target_move_pct,
        "break_even_pct": break_even_pct,
        "risk_level": risk_level,
        "risk_level_reason": risk_level_reason,
        "liquidity_ok": option_estimate.get("weak_liquidity") is not True and option_estimate.get("source") == "live_chain",
        "confidence": "high" if option_estimate.get("source") == "live_chain" else "low",
        "payoff_table": build_call_payoff_table(
            float(current_price),
            strike,
            premium_estimate,
            target=target,
            break_even=break_even,
        ),
        "estimated_option_fallback_reason": option_estimate.get("fallback_reason"),
        "estimated_option_weak_liquidity": option_estimate.get("weak_liquidity", False),
        "ignore_liquidity": ignore_liquidity,
    }
    return report


def build_call_recommendation(
    company: Company,
    *,
    maturity_months: int = 9,
    score: float | None = None,
    risk_budget_pct: float = 0.02,
    option_market_data: dict[str, dict[str, float]] | None = None,
    ignore_liquidity: bool = False,
) -> dict[str, Any]:
    """Create a trade-level directional call recommendation from a screened company."""
    current_price = float(getattr(company.market_facts, "current_price", 0.0) or 0.0)
    if current_price <= 0:
        raise ValueError(f"Current price is required to build a call recommendation for {company.ticker}")

    quality_score = float(getattr(getattr(company, "quality", None), "score", 0.0) or 0.0)
    confidence_score = float(score if score is not None else max(quality_score / 100.0, 0.0))
    liquidity_ok, risk_level, iv, volume, open_interest = _option_market_quality(option_market_data, company.ticker)

    option_estimate_kwargs = {}
    if ignore_liquidity:
        option_estimate_kwargs["ignore_liquidity"] = True
    option_estimate = estimate_best_call_contract(
        company.ticker,
        current_price,
        maturity_months,
        **option_estimate_kwargs,
    )
    suggested_strike = float(option_estimate["strike"])
    premium_estimate = float(option_estimate.get("premium_estimate", 0.0) or 0.0)
    premium_pct_of_stock = round(float((premium_estimate / max(current_price, 0.01)) * 100.0), 2) if premium_estimate > 0 else 0.0
    if option_estimate.get("source") == "live_chain":
        selected_row = option_estimate.get("selected_row") or {}
        premium_estimate = float(selected_row.get("premium", premium_estimate) or premium_estimate)
        break_even = round(float(selected_row.get("break_even", suggested_strike + premium_estimate)), 2)
        max_loss = round(float(min(current_price * risk_budget_pct, premium_estimate * 1.5 if premium_estimate > 0 else current_price * risk_budget_pct)), 2)
    else:
        max_loss = round(float(min(current_price * risk_budget_pct, premium_estimate * 1.5 if premium_estimate > 0 else current_price * risk_budget_pct)), 2)
        break_even = round(float(option_estimate.get("break_even", suggested_strike + max_loss)), 2)
    target = round(
        float(current_price * (1.0 + (0.18 if maturity_months <= 6 else 0.22 if maturity_months <= 9 else 0.28))),
        2,
    )
    target_move_pct = round(float(((target - current_price) / max(current_price, 0.01)) * 100.0), 2)
    break_even_pct = round(float(((break_even - current_price) / max(current_price, 0.01)) * 100.0), 2)
    stop = round(float(current_price * 0.92), 2)
    delta_target = {6: 0.55, 9: 0.50, 12: 0.45}.get(maturity_months, 0.50)

    thesis = (
        f"Directional call on {company.name or company.ticker} driven by quality, "
        f"intrinsic valuation ({getattr(company.reverse_dcf, 'assessment', 'Unavailable')}), "
        f"and improving market conditions."
    )

    if option_estimate.get("source") == "heuristic":
        if not liquidity_ok and ignore_liquidity:
            trade_status = "heuristic fallback: ignoring the strict liquidity gate to show the numbers anyway"
        elif not liquidity_ok:
            trade_status = "heuristic fallback plus liquidity warning: live option chain is unavailable and the option chain is too weak for a controlled trade"
        else:
            trade_status = "heuristic fallback: live option chain is unavailable; treat as watch only"
    elif option_estimate.get("weak_liquidity"):
        trade_status = (
            "live-chain best effort: option chain exists but liquidity is weak; "
            + ("ignoring the strict liquidity gate to show the numbers anyway" if ignore_liquidity else "treat as watch only")
        )
    elif not liquidity_ok:
        trade_status = (
            "liquidity warning: avoid or defer until option chain improves"
            if not ignore_liquidity
            else "liquidity warning: ignoring the strict liquidity gate to show the numbers anyway"
        )
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
        "premium_pct_of_stock": premium_pct_of_stock,
        "target_move_pct": target_move_pct,
        "break_even_pct": break_even_pct,
        "confidence": _confidence_label(confidence_score),
        "liquidity_ok": liquidity_ok,
        "risk_level": risk_level,
        "risk_level_reason": _risk_level_reason(
            risk_level,
            weak_liquidity=bool(option_estimate.get("weak_liquidity", False)),
            iv=iv,
            volume=volume,
            open_interest=open_interest,
        ),
        "ignore_liquidity": ignore_liquidity,
        "trade_status": trade_status,
        "iv": iv,
        "volume": volume,
        "open_interest": open_interest,
        "premium_estimate": premium_estimate,
        "estimated_option_source": option_estimate.get("source", "heuristic"),
        "estimated_option_expiry": option_estimate.get("expiry"),
        "estimated_option_fallback_reason": option_estimate.get("fallback_reason"),
        "estimated_option_weak_liquidity": option_estimate.get("weak_liquidity", False),
    }
    return finalize_trade_decision(recommendation)


def build_call_recommendations(
    companies: list[Company],
    screened_candidates: list[dict[str, Any]],
    option_market_data: dict[str, dict[str, float]] | None = None,
    *,
    ignore_liquidity: bool = False,
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
            ignore_liquidity=ignore_liquidity,
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
