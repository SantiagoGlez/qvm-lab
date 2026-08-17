"""Market signals.

Responsibilities
----------------
- Interpret MarketFacts into qualitative signals.
- All business thresholds live here — not in service.py or the report.

Signals produced
----------------
Trend            : Bullish / Neutral / Bearish
Relative Strength: Strong / Average / Weak
Pullback         : Deep / Moderate / None
Recommendation   : BUY / WATCH / AVOID
"""

from __future__ import annotations

from .models import MarketFacts, MarketSignals


def compute_signals(facts: MarketFacts) -> MarketSignals:
    """Convert raw MarketFacts into interpreted MarketSignals."""
    trend             = _signal_trend(facts)
    relative_strength = _signal_relative_strength(facts)
    pullback          = _signal_pullback(facts)

    assessment     = _compute_assessment(trend, relative_strength, pullback)
    reason         = _generate_reason(trend, relative_strength, pullback, assessment)
    summary        = _build_summary(facts, trend, relative_strength, pullback)

    return MarketSignals(
        trend=trend,
        relative_strength=relative_strength,
        pullback=pullback,
        score=0.0,
        assessment=assessment,
        reason=reason,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Individual signal rules — thresholds TBD in next step
# ---------------------------------------------------------------------------

def _signal_trend(facts: MarketFacts) -> str:
    """Determine price trend from SMA relationship.

    Excellent  Price > SMA50 > SMA200
    Strong     Price > SMA200 (but not both MAs aligned)
    Neutral    Price within ±2% of SMA200
    Weak       Price < SMA200 (beyond the ±2% band)
    """
    price = facts.current_price
    sma50 = facts.sma_50
    sma200 = facts.sma_200

    if price is None or sma200 is None:
        return "Unknown"

    distance = (price - sma200) / sma200

    if sma50 is not None and price > sma50 and sma50 > sma200:
        return "Excellent"

    if price > sma200:
        return "Strong"

    if abs(distance) <= 0.02:
        return "Neutral"

    return "Weak"


def _signal_relative_strength(facts: MarketFacts) -> str:
    """Assess momentum via outperformance vs SPY.

    Uses the average of 6M and 12M relative returns when both are available,
    otherwise falls back to whichever is present.

    Excellent  RS > +20%
    Strong     RS +10% to +20%
    Neutral    RS -10% to +10%
    Weak       RS < -10%
    """
    rs6  = facts.rs_6m
    rs12 = facts.rs_12m

    available = [r for r in (rs6, rs12) if r is not None]
    if not available:
        return "Unknown"

    rs = sum(available) / len(available)

    if rs > 0.20:
        return "Excellent"
    if rs > 0.10:
        return "Strong"
    if rs >= -0.10:
        return "Neutral"
    return "Weak"


def _signal_pullback(facts: MarketFacts) -> str:
    """Classify distance from 52-week high.

    New High   Current Price >= 52W High (at or above)
    Neutral    0% to -10%
    Excellent  -10% to -20%  (ideal entry zone)
    Strong     -20% to -35%
    Weak       < -35%        (broken down / distressed)
    """
    dist = facts.distance_from_52w_high_pct
    if dist is None:
        return "Unknown"

    if dist >= 0:
        return "New High"
    if dist >= -0.10:
        return "Neutral"
    if dist >= -0.20:
        return "Excellent"
    if dist >= -0.35:
        return "Strong"
    return "Weak"


def _compute_score(facts: MarketFacts) -> float:
    """No composite score for Momentum — reserved for future use."""
    return 0.0


# Tier constants for the recommendation table
_STRONG  = 2
_NEUTRAL = 1
_WEAK    = 0


def _tier(signal: str) -> int:
    """Map a signal label to a tier integer."""
    if signal in ("Excellent", "Strong", "New High"):
        return _STRONG
    if signal == "Neutral":
        return _NEUTRAL
    if signal == "Weak":
        return _WEAK
    return _NEUTRAL  # Unknown → treated as Neutral


def _compute_assessment(trend: str, rs: str, pullback: str) -> str:
    """Overall market assessment.

    Attractive
        Strong trend + strong relative strength + healthy pullback.

    Near-highs
        Strong trend + strong relative strength but little/no pullback.

    Improving
        Trend is already positive but relative strength is still catching up.

    Recovering
        Trend has stabilized (Neutral) after a meaningful pullback.

    Weak
        Trend is still negative regardless of pullback.
    """

    trend_t = _tier(trend)
    rs_t = _tier(rs)
    pull_t = _tier(pullback)

    if trend_t >= _STRONG and rs_t >= _STRONG:
        if pull_t >= _STRONG:
            return "Attractive"
        return "Near-highs"

    if trend_t >= _STRONG:
        return "Improving"

    if trend == "Neutral" and pull_t >= _STRONG:
        return "Recovering"

    return "Weak"

_TREND_SENTENCE = {
    "Excellent": "Long-term momentum is very strong, with price above both the 50-day and 200-day moving averages.",
    "Strong": "The long-term trend remains positive, with price above the 200-day moving average.",
    "Neutral": "The stock is trading around its long-term trend with no clear directional advantage.",
    "Weak": "The long-term trend remains negative, with price below the 200-day moving average.",
    "Unknown": "Trend information is unavailable.",
}

_RS_SENTENCE = {
    "Excellent": "The stock is significantly outperforming the broader market.",
    "Strong": "The stock continues to outperform the broader market.",
    "Neutral": "Performance is broadly in line with the market.",
    "Weak": "The stock is lagging the broader market.",
    "Unknown": "Relative strength information is unavailable.",
}

_PULLBACK_SENTENCE = {
    "New High": "The stock is trading at new highs, leaving little margin for an attractive entry.",
    "Neutral": "The stock remains close to its recent highs.",
    "Excellent": "The recent pullback provides an attractive potential entry area.",
    "Strong": "The stock has corrected materially, improving the risk/reward profile.",
    "Weak": "The decline is severe and the chart still requires stabilization.",
    "Unknown": "Pullback information is unavailable.",
}

_ASSESSMENT_CLOSE = {
    "Attractive": "Trend and entry conditions are well aligned.",
    "Near-highs": "Momentum remains strong, but waiting for a pullback may improve the entry.",
    "Improving": "The trend is healthy, although broader momentum is still developing.",
    "Recovering": "Early stabilization is visible after the recent correction.",
    "Weak": "Market conditions remain unfavorable and require patience.",
}

def _generate_reason(
    trend: str,
    rs: str,
    pullback: str,
    assessment: str,
) -> str:
    """Generate a concise explanation of the market assessment."""

    paragraphs = [
        _TREND_SENTENCE.get(trend),
        _RS_SENTENCE.get(rs),
        _PULLBACK_SENTENCE.get(pullback),
        _ASSESSMENT_CLOSE.get(assessment),
    ]

    return " ".join(p for p in paragraphs if p)


def _build_summary(
    facts: MarketFacts,
    trend: str,
    relative_strength: str,
    pullback: str,
) -> str:
    parts = [f"Trend={trend}", f"RS={relative_strength}", f"Pullback={pullback}"]
    if facts.return_12m is not None:
        parts.append(f"12M={facts.return_12m:+.1%}")
    if facts.rsi_14 is not None:
        parts.append(f"RSI={facts.rsi_14:.0f}")
    return " | ".join(parts)
