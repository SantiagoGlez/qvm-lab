from __future__ import annotations

from pydantic import BaseModel


class PortfolioDecision(BaseModel):
    """Structured output of the Portfolio Action layer.

    Each reason section is independent — rendering is the caller's responsibility.
    """

    owned: bool = False
    action: str = ""          # Buy / Watch / Accumulate / Hold / Review / Reduce / Sell

    company_reason: str = ""  # Fundamentals only (Quality + Valuation)
    market_reason: str = ""   # Market state only (Trend + RS + Pullback + Assessment)
    portfolio_reason: str = ""  # Portfolio action only (ownership + action)
