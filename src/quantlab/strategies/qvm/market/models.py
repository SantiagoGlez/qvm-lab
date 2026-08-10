from __future__ import annotations

from pydantic import BaseModel


class MarketFacts(BaseModel):
    """Raw market metrics computed from historical price data.

    Populated by service.py — no business rules here.
    """

    # --- Price levels ---------------------------------------------------------
    current_price: float | None = None
    price_52w_high: float | None = None
    price_52w_low: float | None = None

    # --- Returns (simple, not annualised) ------------------------------------
    return_1m: float | None = None   # ~21 trading days
    return_3m: float | None = None   # ~63 trading days
    return_6m: float | None = None   # ~126 trading days
    return_12m: float | None = None  # ~252 trading days

    # --- Relative strength vs SPY (stock return − SPY return) ---------------
    spy_return_6m: float | None = None
    spy_return_12m: float | None = None
    rs_6m: float | None = None   # return_6m  − spy_return_6m
    rs_12m: float | None = None  # return_12m − spy_return_12m

    # --- Moving averages (price) ----------------------------------------------
    sma_50: float | None = None
    sma_200: float | None = None

    # --- Momentum / mean-reversion indicators --------------------------------
    rsi_14: float | None = None                  # 0-100
    distance_from_52w_high_pct: float | None = None  # negative = below high
    distance_from_sma_200_pct: float | None = None   # positive = above SMA200

    # --- Volatility -----------------------------------------------------------
    volatility_30d: float | None = None  # annualised std dev of daily returns

    # --- Lookback used to compute these metrics -------------------------------
    price_history_days: int | None = None


class MarketSignals(BaseModel):
    """Interpreted market signals derived from MarketFacts.

    Populated by signals.py — business rules live here.
    """

    # --- Signal labels --------------------------------------------------------
    trend: str | None = None              # Excellent / Strong / Neutral / Weak
    relative_strength: str | None = None  # Excellent / Strong / Neutral / Weak
    pullback: str | None = None           # New High / Excellent / Strong / Neutral / Weak

    # --- Composite output -----------------------------------------------------
    score: float = 0.0
    assessment: str = ""   # Attractive / Extended / Improving / Recovering / Weak
    summary: str = ""
    reason: str = ""
