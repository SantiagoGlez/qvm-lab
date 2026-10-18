from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from quantlab.strategies.qvm.models import Company


_INTINSIC_SCORE = {
    "very conservative expectations": 1.00,
    "conservative expectations": 0.90,
    "reasonable expectations": 0.80,
    "optimistic expectations": 0.55,
    "very optimistic expectations": 0.25,
    "unavailable": 0.10,
}

_HISTORICAL_SCORE = {
    "deep value": 1.00,
    "cheap": 0.90,
    "fair value": 0.80,
    "expensive": 0.35,
    "very expensive": 0.05,
    "unavailable": 0.15,
}

_MARKET_SCORE = {
    "attractive": 1.00,
    "improving": 0.90,
    "stabilizing": 0.75,
    "recovering": 0.70,
    "neutral": 0.55,
    "weak": 0.10,
    "unknown": 0.25,
}

_ACTION_SCORE = {
    "add": 1.00,
    "candidate to add": 0.90,
    "watch": 0.75,
    "keep": 0.60,
    "keep (monitor)": 0.60,
    "review": 0.45,
    "add slow": 0.65,
    "reject": 0.00,
    "exit": 0.00,
}


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _score_background(company: Company) -> float:
    quality_score = float(getattr(getattr(company, "quality", None), "score", 0.0) or 0.0)
    intrinsic = _normalize(getattr(company.reverse_dcf, "assessment", None))
    historical = _normalize(getattr(company.valuation, "valuation_band", None))
    market = _normalize(getattr(company.momentum, "recommendation", None))
    action = _normalize(str(getattr(getattr(company, "portfolio", None), "action", "") or ""))

    quality_weight = min(max(quality_score / 100.0, 0.0), 1.0)
    intrinsic_weight = _INTINSIC_SCORE.get(intrinsic, 0.2)
    historical_weight = _HISTORICAL_SCORE.get(historical, 0.15)
    market_weight = _MARKET_SCORE.get(market, 0.25)
    action_weight = _ACTION_SCORE.get(action, 0.20)

    return (
        0.40 * quality_weight
        + 0.30 * intrinsic_weight
        + 0.15 * historical_weight
        + 0.10 * market_weight
        + 0.05 * action_weight
    )


def _is_candidate_eligible(company: Company) -> bool:
    quality_score = float(getattr(getattr(company, "quality", None), "score", 0.0) or 0.0)
    intrinsic = _normalize(getattr(company.reverse_dcf, "assessment", None))
    historical = _normalize(getattr(company.valuation, "valuation_band", None))
    market = _normalize(getattr(company.momentum, "recommendation", None))
    action = _normalize(str(getattr(getattr(company, "portfolio", None), "action", "") or ""))

    if quality_score < 70:
        return False
    if intrinsic in {"very optimistic expectations"}:
        return False
    if historical in {"very expensive", "expensive"}:
        return False
    if market in {"weak"}:
        return False
    if action in {"reject", "exit"}:
        return False
    return True


def _maturity_tilt(maturity_months: int) -> float:
    if maturity_months == 6:
        return 0.95
    if maturity_months == 9:
        return 1.00
    if maturity_months == 12:
        return 1.05
    return 1.00


def _option_market_factor(option_market_data: dict[str, dict[str, float]] | None, ticker: str) -> float:
    if option_market_data is None:
        return 1.0

    metrics = option_market_data.get(ticker.upper())
    if not metrics:
        return 1.0

    iv = float(metrics.get("iv", 0.0) or 0.0)
    volume = float(metrics.get("volume", 0.0) or 0.0)
    open_interest = float(metrics.get("open_interest", 0.0) or 0.0)

    factor = 1.0
    if iv > 0.9:
        factor *= 0.35
    elif iv > 0.7:
        factor *= 0.60
    elif iv > 0.5:
        factor *= 0.80

    if volume > 0 and volume < 250_000:
        factor *= 0.75
    elif volume > 0 and volume < 1_000_000:
        factor *= 0.90

    if open_interest > 0 and open_interest < 1_000:
        factor *= 0.75
    elif open_interest > 0 and open_interest < 5_000:
        factor *= 0.90

    return max(0.0, min(factor, 1.0))


def screen_call_candidates(
    companies: Iterable[Company],
    maturities: Iterable[int] | None = None,
    top_n: int = 10,
    option_market_data: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Return a ranked shortlist of call candidates for 6, 9 and 12 month horizons.

    The base logic is intentionally conservative. Optional option-market metrics are
    applied only when they are available and are used as a penalty layer rather than
    a primary ranking signal.
    """
    maturity_list = list(maturities) if maturities is not None else [6, 9, 12]
    candidates: list[dict[str, Any]] = []

    for company in companies:
        if not _is_candidate_eligible(company):
            continue

        option_factor = _option_market_factor(option_market_data, company.ticker)
        if option_factor <= 0.25:
            continue

        background_score = _score_background(company)
        for maturity_months in maturity_list:
            maturity_score = background_score * option_factor * _maturity_tilt(maturity_months)
            if maturity_score <= 0:
                continue

            candidates.append(
                {
                    "ticker": company.ticker,
                    "name": company.name or company.ticker,
                    "quality_score": float(getattr(getattr(company, "quality", None), "score", 0.0) or 0.0),
                    "intrinsic_assessment": getattr(company.reverse_dcf, "assessment", "Unavailable"),
                    "historical_valuation": getattr(company.valuation, "valuation_band", "Unavailable"),
                    "market_assessment": getattr(company.momentum, "recommendation", "Unknown"),
                    "portfolio_action": getattr(getattr(company, "portfolio", None), "action", ""),
                    "maturity_months": int(maturity_months),
                    "score": round(float(maturity_score), 3),
                    "option_market_factor": round(float(option_factor), 3),
                    "reason": (
                        "Quality and intrinsic setup support a directional call; "
                        f"historical valuation={getattr(company.valuation, 'valuation_band', 'Unavailable')} "
                        f"and market={getattr(company.momentum, 'recommendation', 'Unknown')}"
                    ),
                }
            )

    ordered = sorted(candidates, key=lambda row: (-float(row["score"]), row["ticker"]))
    return ordered[:top_n]
