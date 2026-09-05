"""Portfolio Action layer.

Responsibilities
----------------
- Combine Valuation, Quality, Market Assessment and ownership to
  produce a deterministic Portfolio Action and three independent reason sections.
- All business rules and templates live here.
- No LLM, no external calls.

Actions
-------
Not owned  : Add | Add Slow | Candidate to Add | Watch | Reject
Owned      : Add | Add Slow | Keep | Keep (Monitor) | Review | Exit
"""

from __future__ import annotations

from .models import PortfolioDecision
from .service import owns

# ---------------------------------------------------------------------------
# Fundamentals tier thresholds
# ---------------------------------------------------------------------------

_EXCELLENT_QUALITY = 75.0
_AVERAGE_QUALITY   = 55.0
_WEAK_QUALITY      = 35.0


def _fundamentals_tier(quality_score: float) -> str:
    if quality_score >= _EXCELLENT_QUALITY:
        return "Excellent"
    if quality_score >= _AVERAGE_QUALITY:
        return "Average"
    if quality_score >= _WEAK_QUALITY:
        return "Weak"
    return "Broken"


# ---------------------------------------------------------------------------
# Company reason templates (Quality + Valuation)
# ---------------------------------------------------------------------------

_QUALITY_FRAGMENT = {
    "Excellent": (
        "High-quality business with durable profitability, strong capital allocation "
        "and healthy cash generation."
    ),
    "Average": (
        "Solid business with resilient fundamentals, although not all quality "
        "characteristics stand out."
    ),
    "Weak": (
        "Business quality is below the desired standard, with weaknesses across "
        "profitability, growth or financial strength."
    ),
    "Broken": (
        "The business shows material fundamental deterioration requiring a review "
        "of the investment thesis."
    ),
}

_VALUATION_FRAGMENT = {
    "Deep Value":
        "The shares trade well below their historical valuation range.",

    "Cheap":
        "The shares trade below their long-term historical valuation.",

    "Fair Value":
        "The shares trade broadly in line with their historical valuation.",

    "Expensive":
        "The shares trade above their historical valuation range.",

    "Very Expensive":
        "The shares trade materially above their historical valuation range.",
}


def _build_company_reason(quality_tier: str, valuation_band: str | None) -> str:
    quality_frag   = _QUALITY_FRAGMENT.get(quality_tier, "")
    valuation_frag = _VALUATION_FRAGMENT.get(valuation_band or "", "")
    return " ".join(s for s in (quality_frag, valuation_frag) if s)


# ---------------------------------------------------------------------------
# Market reason templates (Trend + RS + Pullback)
# ---------------------------------------------------------------------------

_TREND_FRAGMENT: dict[str, str] = {
    "Excellent": "Long-term and short-term trends are both aligned",
    "Strong":    "The long-term trend remains healthy",
    "Neutral":   "Price is hovering near its long-term moving average",
    "Weak":      "The long-term trend has turned negative",
    "Unknown":   "Trend data is unavailable",
}

_RS_FRAGMENT: dict[str, str] = {
    "Excellent": "the stock is strongly outperforming the broader market",
    "Strong":    "the stock continues to outperform the market",
    "Neutral":   "the stock is performing broadly in line with the market",
    "Weak":      "the stock is underperforming the broader market",
    "Unknown":   "relative strength data is unavailable",
}

_PULLBACK_FRAGMENT: dict[str, str] = {
    "New High":  "Shares are making new 52-week highs — momentum is strong.",
    "Excellent": "Shares have pulled back to an attractive entry zone off the 52-week high.",
    "Strong":    "Shares have corrected materially from the 52-week high.",
    "Neutral":   "Shares are trading close to their 52-week high with minimal pullback.",
    "Weak":      "Shares have fallen sharply from the 52-week high — caution is warranted.",
    "Unknown":   "",
}


def _build_market_reason(trend: str, rs: str, pullback: str) -> str:
    trend_frag = _TREND_FRAGMENT.get(trend, "")
    rs_frag = _RS_FRAGMENT.get(rs, "")
    pullback_sent = _PULLBACK_FRAGMENT.get(pullback, "")

    first = ""
    if trend_frag and rs_frag:
        first = f"{trend_frag} and {rs_frag}."
    elif trend_frag:
        first = f"{trend_frag}."
    elif rs_frag:
        first = f"{rs_frag.capitalize()}."

    return " ".join(s for s in (first, pullback_sent) if s)


_ACCEPTABLE_VALUATION_BANDS = {"deep value", "cheap", "fair value"}
_MAJOR_VALUATION_WARNING_BANDS = {"very expensive"}
_MILD_VALUATION_WARNING_BANDS = {"expensive"}
_SUPPORTIVE_INTRINSIC = {
    "very conservative expectations",
    "conservative expectations",
    "reasonable expectations",
}
_INTRINSIC_WARNING = {"very optimistic expectations"}


def _normalize_label(value: str | None) -> str:
    return (value or "").strip().lower()


def _historical_valuation_ok(valuation_band: str | None) -> bool:
    return _normalize_label(valuation_band) in _ACCEPTABLE_VALUATION_BANDS


def _major_valuation_warning(valuation_band: str | None) -> bool:
    return _normalize_label(valuation_band) in _MAJOR_VALUATION_WARNING_BANDS


def _mild_valuation_warning(valuation_band: str | None) -> bool:
    return _normalize_label(valuation_band) in _MILD_VALUATION_WARNING_BANDS


def _intrinsic_supportive(intrinsic_assessment: str | None) -> bool:
    return _normalize_label(intrinsic_assessment) in _SUPPORTIVE_INTRINSIC


def _intrinsic_warning(intrinsic_assessment: str | None) -> bool:
    return _normalize_label(intrinsic_assessment) in _INTRINSIC_WARNING


def _supports_normal_add(assessment: str) -> bool:
    return assessment in {"Attractive", "Improving"}


def _supports_slow_add(assessment: str) -> bool:
    return assessment in {"Recovering", "Neutral"}


def _valuation_supportive_on_balance(
    valuation_band: str | None,
    intrinsic_assessment: str | None,
) -> bool:
    # One supportive valuation lens is enough to allow a reserve entry candidate.
    return _historical_valuation_ok(valuation_band) or _intrinsic_supportive(intrinsic_assessment)


def _valuation_confirmed_for_add(
    valuation_band: str | None,
    intrinsic_assessment: str | None,
) -> bool:
    historical_ok = _historical_valuation_ok(valuation_band)
    intrinsic_ok = _intrinsic_supportive(intrinsic_assessment)
    major_warning = _major_valuation_warning(valuation_band)
    intrinsic_warning = _intrinsic_warning(intrinsic_assessment)

    # Strict Add confirmation: both supportive, or one supportive while the other is not warning.
    return (
        (historical_ok and intrinsic_ok)
        or (historical_ok and not intrinsic_warning)
        or (intrinsic_ok and not major_warning)
    )


def _double_valuation_warning(
    valuation_band: str | None,
    intrinsic_assessment: str | None,
) -> bool:
    return _major_valuation_warning(valuation_band) and _intrinsic_warning(intrinsic_assessment)


def _quality_stance(tier: str) -> str:
    if tier == "Excellent":
        return "Quality remains high"
    if tier == "Average":
        return "Quality is acceptable but not top-tier"
    if tier == "Weak":
        return "Quality is weak versus preferred candidates"
    return "Quality appears fundamentally broken"


def _historical_valuation_stance(valuation_band: str | None) -> str:
    normalized = _normalize_label(valuation_band)
    if normalized in _ACCEPTABLE_VALUATION_BANDS:
        return "Historical valuation is acceptable"
    if normalized in _MAJOR_VALUATION_WARNING_BANDS:
        return "Historical valuation is a major warning"
    if normalized:
        return "Historical valuation is stretched"
    return "Historical valuation is unavailable"


def _intrinsic_stance(intrinsic_assessment: str | None) -> str:
    if _intrinsic_supportive(intrinsic_assessment):
        return "Intrinsic valuation is supportive"
    if _intrinsic_warning(intrinsic_assessment):
        return "Intrinsic valuation is a warning"
    if intrinsic_assessment:
        return "Intrinsic valuation is neutral"
    return "Intrinsic valuation is unavailable"


def _market_stance(assessment: str) -> str:
    if _supports_normal_add(assessment):
        return "Market assessment supports normal pacing"
    if _supports_slow_add(assessment):
        return "Market assessment supports gradual pacing"
    if assessment == "Weak":
        return "Market assessment is weak and lowers conviction"
    return "Market assessment is mixed"


def _signal_snapshot(
    tier: str,
    valuation_band: str | None,
    intrinsic_assessment: str | None,
    assessment: str,
) -> str:
    return "; ".join(
        (
            _quality_stance(tier),
            _historical_valuation_stance(valuation_band),
            _intrinsic_stance(intrinsic_assessment),
            _market_stance(assessment),
        )
    ) + "."
# ---------------------------------------------------------------------------
# Portfolio reason templates (ownership + action)
# ---------------------------------------------------------------------------

_PORTFOLIO_REASON: dict[tuple[bool, str], str] = {
    # ---------- Not owned ----------
    (
        False,
        "Add",
    ): (
        "The company ranks as a strong candidate for fresh capital now. "
        "Deploy capital with normal pacing based on overall conviction."
    ),
    (
        False,
        "Add Slow",
    ): (
        "The company looks attractive fundamentally, but the current setup supports "
        "a gradual entry rather than a full-sized add today."
    ),
    (
        False,
        "Candidate to Add",
    ): (
        "The company stays on a prioritized reserve list. It is not a full add today, "
        "but it should be revisited first when stronger add capacity is limited."
    ),
    (
        False,
        "Watch",
    ): (
        "Keep the company on the watchlist while stronger candidates receive priority "
        "for fresh capital."
    ),
    (
        False,
        "Reject",
    ): (
        "The company does not currently clear the bar relative to the best available "
        "alternatives."
    ),

    # ---------- Owned ----------
    (
        True,
        "Add",
    ): (
        "The original investment thesis remains intact and this holding still merits "
        "new capital at a normal pace."
    ),
    (
        True,
        "Add Slow",
    ): (
        "The original investment thesis remains intact, but current conditions favor "
        "building the position gradually."
    ),
    (
        True,
        "Keep",
    ): (
        "The original investment thesis remains intact. No forced portfolio action is "
        "required today."
    ),
    (
        True,
        "Exit",
    ): (
        "The original investment thesis is no longer supported. Consider exiting "
        "the position."
    ),
}


def _build_portfolio_reason(
    owned: bool,
    action: str,
    tier: str,
    valuation_band: str | None,
    intrinsic_assessment: str | None,
    assessment: str,
) -> str:
    snapshot = _signal_snapshot(tier, valuation_band, intrinsic_assessment, assessment)
    double_warning = _double_valuation_warning(valuation_band, intrinsic_assessment)

    if not owned and action == "Reject" and double_warning:
        return (
            "Avoid new capital for now because both valuation lenses are in warning mode. "
            f"{snapshot} "
            "This is a hard stop until valuation risk normalizes."
        )

    if not owned and action == "Watch":
        if assessment == "Near-highs":
            return (
                "Keep on watchlist and wait for a better entry window rather than chasing strength. "
                f"{snapshot} "
                "Timing is the primary constraint, not business quality."
            )
        return (
            "Keep on watchlist while waiting for clearer confirmation versus current add candidates. "
            f"{snapshot}"
        )

    if owned and action == "Keep (Monitor)":
        return (
            "Hold the position with caution rather than rotating now. "
            f"{snapshot} "
            "A mild warning is present, but conviction remains positive, so this is not "
            "yet a replacement case."
        )

    if owned and action == "Review":
        return (
            "Reassess the holding against current alternatives and treat it as the first "
            "potential funding source if a stronger replacement appears. "
            f"{snapshot} "
            "Relative conviction is lower versus the best available candidates."
        )

    template = _PORTFOLIO_REASON.get((owned, action), "")
    if not template:
        return ""

    if owned:
        return f"{template} {snapshot}"
    return f"{template} {snapshot}"


# ---------------------------------------------------------------------------
# Action rules
# ---------------------------------------------------------------------------

def _action_not_owned(
    tier: str,
    valuation_band: str | None,
    intrinsic_assessment: str | None,
    assessment: str,
) -> str:
    if tier in {"Broken", "Weak"}:
        return "Reject"

    valuation_supportive = _valuation_supportive_on_balance(valuation_band, intrinsic_assessment)
    valuation_confirmed = _valuation_confirmed_for_add(valuation_band, intrinsic_assessment)
    double_warning = _double_valuation_warning(valuation_band, intrinsic_assessment)
    market_normal_add = _supports_normal_add(assessment)
    market_slow_add = _supports_slow_add(assessment)

    if double_warning:
        return "Reject"

    if tier == "Excellent":
        if market_normal_add and valuation_confirmed:
            return "Add"
        if market_slow_add and valuation_confirmed:
            return "Add Slow"

        # Reserve queue for near-add cases: strong quality and decent market,
        # but valuation confirmation is only partial.
        if (market_normal_add or market_slow_add) and valuation_supportive and not valuation_confirmed:
            return "Candidate to Add"
        return "Watch"

    return "Watch"


def _action_owned(
    tier: str,
    valuation_band: str | None,
    intrinsic_assessment: str | None,
    assessment: str,
) -> str:
    if tier == "Broken":
        return "Exit"

    major_valuation_warning = _major_valuation_warning(valuation_band)
    mild_valuation_warning = _mild_valuation_warning(valuation_band)
    intrinsic_warning = _intrinsic_warning(intrinsic_assessment)
    valuation_supportive = _valuation_supportive_on_balance(valuation_band, intrinsic_assessment)
    market_weak = assessment == "Weak"
    warning_count = (
        int(major_valuation_warning)
        + int(mild_valuation_warning)
        + int(intrinsic_warning)
        + int(market_weak)
    )

    if tier == "Weak" and major_valuation_warning:
        return "Exit"

    if tier == "Excellent" and valuation_supportive:
        if _supports_normal_add(assessment):
            return "Add"
        if _supports_slow_add(assessment):
            return "Add Slow"

    if tier == "Excellent":
        if not valuation_supportive or warning_count == 1:
            return "Keep (Monitor)"
        if warning_count >= 2:
            return "Review"
        return "Keep"

    if tier == "Average":
        if warning_count == 0 and valuation_supportive:
            return "Keep (Monitor)"
        if market_weak or major_valuation_warning or intrinsic_warning:
            return "Review"
        return "Keep (Monitor)"

    return "Review"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_action(
    ticker: str,
    quality_score: float,
    valuation_band: str | None,
    intrinsic_assessment: str | None,
    assessment: str,
    trend: str,
    rs: str,
    pullback: str,
) -> PortfolioDecision:
    """Compute a deterministic Portfolio Action with structured reason sections."""
    owned = owns(ticker)
    tier  = _fundamentals_tier(quality_score)
    action = (
        _action_not_owned(tier, valuation_band, intrinsic_assessment, assessment)
        if not owned
        else _action_owned(tier, valuation_band, intrinsic_assessment, assessment)
    )

    return PortfolioDecision(
        owned=owned,
        action=action,
        company_reason=_build_company_reason(tier, valuation_band),
        market_reason=_build_market_reason(trend, rs, pullback),
        portfolio_reason=_build_portfolio_reason(
            owned,
            action,
            tier,
            valuation_band,
            intrinsic_assessment,
            assessment,
        ),
    )
