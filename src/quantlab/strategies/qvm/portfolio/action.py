"""Portfolio Action layer.

Responsibilities
----------------
- Combine Valuation, Quality, Market Assessment and ownership to
  produce a deterministic Portfolio Action and three independent reason sections.
- All business rules and templates live here.
- No LLM, no external calls.

Actions
-------
Not owned  : Buy | Watch
Owned      : Accumulate | Hold | Review | Reduce | Sell
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


# def _build_market_reason(trend: str, rs: str, pullback: str) -> str:
#     trend_frag    = _TREND_FRAGMENT.get(trend, "")
#     rs_frag       = _RS_FRAGMENT.get(rs, "")
#     pullback_sent = _PULLBACK_FRAGMENT.get(pullback, "")
#     first = f"{trend_frag} and {rs_frag}." if (trend_frag and rs_frag) else f"{trend_frag}."
#     return " ".join(s for s in (first, pullback_sent) if s)
def _build_market_reason(trend: str, rs: str, pullback: str) -> str:
    return ""
# ---------------------------------------------------------------------------
# Portfolio reason templates (ownership + action)
# ---------------------------------------------------------------------------

_PORTFOLIO_REASON: dict[tuple[bool, str], str] = {
    # ---------- Not owned ----------
    (
        False,
        "Buy",
    ): (
        "The company combines strong fundamentals with favorable market conditions. "
        "Consider initiating a starter position."
    ),
    (
        False,
        "Watch",
    ): (
        "Keep the company on the watchlist and wait for either a more attractive "
        "entry point or stronger market confirmation."
    ),

    # ---------- Owned ----------
    (
        True,
        "Accumulate",
    ): (
        "The original investment thesis remains intact and current conditions "
        "support increasing the existing position."
    ),
    (
        True,
        "Hold",
    ): (
        "The original investment thesis remains intact. No portfolio action is "
        "required today."
    ),
    (
        True,
        "Review",
    ): (
        "Revisit the original investment thesis and confirm that the reasons for "
        "owning the business still hold."
    ),
    (
        True,
        "Reduce",
    ): (
        "Risk has increased since the position was initiated. Consider trimming "
        "the position while reassessing the investment thesis."
    ),
    (
        True,
        "Sell",
    ): (
        "The original investment thesis is no longer supported. Consider exiting "
        "the position."
    ),
}


def _build_portfolio_reason(owned: bool, action: str) -> str:
    return _PORTFOLIO_REASON.get((owned, action), "")


# ---------------------------------------------------------------------------
# Action rules
# ---------------------------------------------------------------------------

def _action_not_owned(tier: str, assessment: str) -> str:
    if tier == "Excellent" and assessment == "Attractive":
        return "Buy"
    return "Watch"


def _action_owned(tier: str, assessment: str) -> str:
    if tier == "Broken":
        return "Sell"
    if tier == "Weak" and assessment == "Weak":
        return "Reduce"
    if tier == "Average" and assessment == "Weak":
        return "Review"
    if tier == "Excellent" and assessment == "Attractive":
        return "Accumulate"
    return "Hold"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_action(
    ticker: str,
    quality_score: float,
    valuation_band: str | None,
    assessment: str,
    trend: str,
    rs: str,
    pullback: str,
) -> PortfolioDecision:
    """Compute a deterministic Portfolio Action with structured reason sections."""
    owned = owns(ticker)
    tier  = _fundamentals_tier(quality_score)
    action = _action_not_owned(tier, assessment) if not owned else _action_owned(tier, assessment)

    return PortfolioDecision(
        owned=owned,
        action=action,
        company_reason=_build_company_reason(tier, valuation_band),
        market_reason=_build_market_reason(trend, rs, pullback),
        portfolio_reason=_build_portfolio_reason(owned, action),
    )
